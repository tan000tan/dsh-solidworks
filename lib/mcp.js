/**
 * Minimal JSON-RPC 2.0 MCP stdio client used by the dsh-solidworks plugin.
 *
 * Scope: exactly the three calls this plugin needs — `initialize`,
 * `tools/list`, `tools/call` — plus cancellation and clean teardown.
 */

import { spawn } from 'node:child_process';

const DEFAULT_TIMEOUT_MS = 120_000;
const STDERR_LINES = 200;
/** Protocol revisions this client knows how to speak (BUG-0013). */
export const SUPPORTED_PROTOCOL_VERSIONS = Object.freeze(['2025-06-18', '2025-03-26', '2024-11-05']);

export class McpError extends Error {
  constructor(code, message, data) {
    super(message);
    this.name = 'McpError';
    this.code = code;
    this.data = data;
  }
}

export class McpClient {
  #child = null;
  #pending = new Map();
  #nextId = 1;
  #buffer = '';
  #stderr = [];
  #closed = false;
  #exitInfo = null;
  #restartFailures = 0;
  #maxRestartAttempts = 3;
  #logger;

  constructor({ command, args = [], cwd, env, logger, maxRestartAttempts = 3 } = {}) {
    this.command = command;
    this.args = args;
    this.cwd = cwd;
    this.env = env ?? {};
    this.#logger = logger;
    this.#maxRestartAttempts = Math.max(0, Number(maxRestartAttempts) || 0);
  }

  get running() {
    return this.#child !== null && !this.#closed && this.#exitInfo === null;
  }

  get exitInfo() {
    return this.#exitInfo;
  }

  /** Recent child stderr, newest last, for error surfaces and `doctor`. */
  stderrTail(limit = 20) {
    return this.#stderr.slice(-limit);
  }

  start() {
    if (this.#child) return this;
    // C-MCP-03: a fresh child means a fresh byte stream. Any bytes still in the
    // frame buffer belong to the process that just died; keeping them makes the
    // first reply of the new process unparsable (observed: a truncated frame
    // prefix glued onto the initialize result), which silently costs a full
    // startTimeout and leaves the client "running" but requestless.
    this.#buffer = '';
    const child = spawn(this.command, this.args, {
      cwd: this.cwd,
      env: { PYTHONDONTWRITEBYTECODE: '1', ...process.env, ...this.env },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.#child = child;
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => this.#onStdout(chunk));
    child.stderr.on('data', chunk => this.#onStderr(chunk));
    child.on('error', error => this.#shutdown(new McpError('SPAWN_FAILED', `Cannot start ${this.command}: ${error.message}`)));
    child.on('exit', (code, signal) => this.#shutdown(new McpError('SERVER_EXITED', `MCP server exited (code=${code}, signal=${signal ?? 'none'})`), { code, signal }));
    return this;
  }

  async initialize({ clientName = 'dsh-solidworks', clientVersion = '0.0.0', protocolVersion = '2025-06-18', timeoutMs } = {}) {
    this.start();
    const result = await this.request('initialize', {
      protocolVersion,
      capabilities: {},
      clientInfo: { name: clientName, version: clientVersion },
    }, { timeoutMs });
    // BUG-0013: validate negotiated protocolVersion against supported whitelist.
    const negotiated = result?.protocolVersion;
    if (typeof negotiated === 'string' && !SUPPORTED_PROTOCOL_VERSIONS.includes(negotiated)) {
      throw new McpError(
        'PROTOCOL_VERSION_UNSUPPORTED',
        `MCP server negotiated unsupported protocol version ${negotiated} (supported: ${SUPPORTED_PROTOCOL_VERSIONS.join(', ')})`,
      );
    }
    this.protocolVersion = typeof negotiated === 'string' ? negotiated : protocolVersion;
    this.#restartFailures = 0;
    this.notify('notifications/initialized');
    return result;
  }

  async listTools({ timeoutMs } = {}) {
    const result = await this.request('tools/list', {}, { timeoutMs });
    return Array.isArray(result?.tools) ? result.tools : [];
  }

  async callTool(name, args = {}, { timeoutMs, signal } = {}) {
    if (!this.running && !this.#closed) {
      if (this.#restartFailures >= this.#maxRestartAttempts) {
        throw new McpError(
          'RESTART_LIMIT_EXCEEDED',
          `MCP server failed automatic restart ${this.#restartFailures} times consecutively; refusing further automatic restarts.`,
          this.#exitInfo,
        );
      }
      this.#restartFailures += 1;
      // BUG-0011: reset child/exit state and attempt one automatic restart.
      this.#logger?.info?.('dsh-solidworks: MCP server not running, attempting one restart...');
      this.#exitInfo = null;
      this.#child = null;
      try {
        await this.initialize({ timeoutMs: Math.min(timeoutMs ?? DEFAULT_TIMEOUT_MS, 30_000) });
      } catch (recoveryErr) {
        this.#logger?.warn?.(`dsh-solidworks: automatic restart failed: ${recoveryErr.message}`);
      }
    }
    const result = await this.request('tools/call', { name, arguments: args }, { timeoutMs, signal });
    this.#restartFailures = 0;
    return {
      isError: result?.isError === true,
      content: Array.isArray(result?.content) ? result.content : [],
      structured: result?.structuredContent ?? null,
    };
  }

  request(method, params = {}, { timeoutMs = DEFAULT_TIMEOUT_MS, signal } = {}) {
    if (!this.running) {
      const info = this.#exitInfo;
      const reason = info
        ? `MCP server exited (code=${info.code}, signal=${info.signal ?? 'none'})`
        : 'MCP client is not running (never started, or closed)';
      return Promise.reject(new McpError(info ? 'SERVER_EXITED' : 'NOT_RUNNING', reason));
    }
    const id = this.#nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(id);
        // C-MCP-04: a timeout is a cancellation from the server's point of view.
        // Without this the CAD side keeps executing (a 5-minute solve keeps
        // running), the result is dropped on the floor and the next call queues
        // behind it. Mirror what the abort path already does.
        this.notify('notifications/cancelled', { requestId: id, reason: 'timeout' });
        reject(new McpError('TIMEOUT', `${method} timed out after ${timeoutMs}ms`));
      }, Math.max(1, timeoutMs));
      timer.unref?.();
      const onAbort = () => {
        this.#pending.delete(id);
        clearTimeout(timer);
        this.notify('notifications/cancelled', { requestId: id, reason: 'client cancelled' });
        reject(new McpError('CANCELLED', `${method} was cancelled`));
      };
      if (signal) {
        if (signal.aborted) { onAbort(); return; }
        signal.addEventListener('abort', onAbort, { once: true });
      }
      this.#pending.set(id, {
        resolve: value => { clearTimeout(timer); signal?.removeEventListener?.('abort', onAbort); resolve(value); },
        reject: error => { clearTimeout(timer); signal?.removeEventListener?.('abort', onAbort); reject(error); },
      });
      this.#write({ jsonrpc: '2.0', id, method, params });
    });
  }

  notify(method, params = {}) {
    if (!this.running) return;
    this.#write({ jsonrpc: '2.0', method, params });
  }

  async close({ timeoutMs = 3000 } = {}) {
    if (this.#closed) return;
    this.#closed = true;
    const child = this.#child;
    this.#child = null;
    this.#rejectAll(new McpError('CLOSED', 'MCP client closed'));
    if (!child || child.exitCode !== null) return;
    try { child.stdin.end(); } catch { /* already gone */ }
    const exited = await new Promise(resolve => {
      const timer = setTimeout(() => resolve(false), timeoutMs);
      timer.unref?.();
      child.once('exit', () => { clearTimeout(timer); resolve(true); });
    });
    if (!exited) { try { child.kill(); } catch { /* ignore */ } }
  }

  #write(message) {
    try {
      this.#child.stdin.write(`${JSON.stringify(message)}\n`);
    } catch (error) {
      this.#logger?.warn?.(`dsh-solidworks: write failed: ${error.message}`);
    }
  }

  #onStdout(chunk) {
    this.#buffer += chunk;
    let index;
    while ((index = this.#buffer.indexOf('\n')) >= 0) {
      const line = this.#buffer.slice(0, index).replace(/\r$/, '');
      this.#buffer = this.#buffer.slice(index + 1);
      if (line.trim() === '') continue;
      if (!line.startsWith('{')) { this.#note(`stdout: ${line.slice(0, 400)}`); continue; }
      let message;
      try { message = JSON.parse(line); } catch { this.#note(`unparsable stdout line: ${line.slice(0, 400)}`); continue; }
      this.#dispatch(message);
    }
  }

  #dispatch(message) {
    if (message.id === undefined || message.id === null) {
      if (message.method && message.method !== 'notifications/message') {
        this.#note(`server notification: ${message.method}`);
      }
      return;
    }
    const entry = this.#pending.get(message.id);
    if (!entry) return;
    this.#pending.delete(message.id);
    if (message.error) {
      entry.reject(new McpError(message.error.code ?? 'MCP_ERROR', message.error.message ?? 'MCP error', message.error.data));
    } else {
      entry.resolve(message.result ?? {});
    }
  }

  #onStderr(chunk) {
    for (const raw of String(chunk).split(/\r?\n/)) {
      const line = raw.trim();
      if (line !== '') this.#note(line);
    }
  }

  #note(line) {
    this.#stderr.push(line);
    if (this.#stderr.length > STDERR_LINES) this.#stderr.shift();
  }

  #shutdown(error, info = null) {
    if (info) {
      this.#exitInfo = info;
      this.#child = null;
    } else if (!this.#exitInfo) {
      this.#exitInfo = { code: null, signal: null };
    }
    this.#rejectAll(error);
  }

  #rejectAll(error) {
    for (const [, entry] of this.#pending) entry.reject(error);
    this.#pending.clear();
  }
}
