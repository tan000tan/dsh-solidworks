/** Stub MCP server used by tests: newline-delimited JSON-RPC over stdio. */
import process from 'node:process';

const TOOLS = [
  {
    name: 'stub_read',
    description: 'read something',
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'], additionalProperties: false },
  },
  {
    name: 'stub_save',
    description: 'save something',
    inputSchema: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'], additionalProperties: false },
  },
  {
    name: 'stub_slow',
    description: 'never answers',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
];

let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (line) handle(JSON.parse(line));
  }
});

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function handle(message) {
  if (message.id === undefined) return; // notification
  switch (message.method) {
    case 'initialize':
      send({ jsonrpc: '2.0', id: message.id, result: { protocolVersion: '2025-06-18', capabilities: { tools: {} }, serverInfo: { name: 'stub', version: '0.0.1' } } });
      return;
    case 'tools/list':
      send({ jsonrpc: '2.0', id: message.id, result: { tools: TOOLS } });
      return;
    case 'tools/call': {
      const name = message.params?.name;
      if (name === 'stub_read') {
        const content = [{ type: 'text', text: `read ${message.params.arguments?.id}` }];
        send({ jsonrpc: '2.0', id: message.id, result: { content } });
        return;
      }
      if (name === 'stub_save') {
        send({ jsonrpc: '2.0', id: message.id, result: { isError: true, content: [{ type: 'text', text: 'save refused by stub' }] } });
        return;
      }
      if (name === 'stub_slow') return; // deliberately never responds
      send({ jsonrpc: '2.0', id: message.id, error: { code: -32602, message: `unknown tool ${name}` } });
      return;
    }
    default:
      send({ jsonrpc: '2.0', id: message.id, error: { code: -32601, message: `unknown method ${message.method}` } });
  }
}