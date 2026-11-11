import test from 'node:test';
import assert from 'node:assert/strict';
import { apply } from '../lib/index.js';

test('AI self-authorization defense: solidworks_confirm requires cryptographic ticket and fails closed', async () => {
  const registeredTools = new Map();
  const mockCtx = {
    tools: {
      register(def) {
        registeredTools.set(def.name, def);
        return () => registeredTools.delete(def.name);
      },
    },
    agent: {
      session: {
        header: { id: 'test-session-123', cwd: 'D:\\sandbox' },
      },
    },
  };

  await apply(mockCtx, { mode: 'full' });

  const confirmTool = registeredTools.get('solidworks_confirm');
  assert.ok(confirmTool, 'solidworks_confirm must be registered');

  const testTool = 'solidworks_save_document';
  const testArgs = { filepath: 'D:\\sandbox\\part1.sldprt' };

  // Case 1: AI calls without challengeId or ticket -> REFUSED
  const res1 = await confirmTool.execute({
    tool: testTool,
    args: testArgs,
  });
  const data1 = JSON.parse(res1.text);
  assert.equal(data1.status, 'refused');
  assert.equal(data1.code, 'CHALLENGE_INVALID');

  // Case 2: AI attempts legacy bypass with confirmedByHuman: true -> REFUSED (fails closed)
  const res2 = await confirmTool.execute({
    tool: testTool,
    args: testArgs,
    confirmedByHuman: true,
  });
  const data2 = JSON.parse(res2.text);
  assert.equal(data2.status, 'refused');

  // Case 3: AI creates a challenge via policy, then tries to fabricate a ticket -> REFUSED
  const challenge = mockCtx.solidworks.policy.createChallenge(testTool, testArgs, {
    sessionId: 'test-session-123',
  });
  assert.ok(challenge.challengeId, 'challenge must have challengeId');

  const resFabricated = await confirmTool.execute({
    challengeId: challenge.challengeId,
    ticket: 'deadbeefcafebabe1234567890abcdefdeadbeefcafebabe1234567890abcdef',
    tool: testTool,
    args: testArgs,
  });
  const dataFabricated = JSON.parse(resFabricated.text);
  assert.equal(dataFabricated.status, 'refused');
  assert.equal(dataFabricated.code, 'TICKET_INVALID');

  // Case 4: Host/human signs the challenge via trusted local method -> ticket is valid -> GRANTED
  const validTicket = mockCtx.solidworks.signApproval(challenge.challengeId, {
    sessionId: 'test-session-123',
  });
  assert.ok(validTicket, 'host must generate valid HMAC ticket');

  const resValid = await confirmTool.execute({
    challengeId: challenge.challengeId,
    ticket: validTicket,
    tool: testTool,
    args: testArgs,
    reason: '用户在界面确认保存零件',
  });
  const dataValid = JSON.parse(resValid.text);
  assert.equal(dataValid.status, 'granted');
  assert.equal(dataValid.tool, testTool);
  assert.ok(dataValid.digest, 'must return cryptographic digest');

  // Case 5: Replay attack (reusing the same ticket and challenge) -> REFUSED (single-use)
  const resReplay = await confirmTool.execute({
    challengeId: challenge.challengeId,
    ticket: validTicket,
    tool: testTool,
    args: testArgs,
  });
  const dataReplay = JSON.parse(resReplay.text);
  assert.equal(dataReplay.status, 'refused');
  assert.equal(dataReplay.code, 'CHALLENGE_NOT_FOUND');

  // Clean exit
  process.exit(0);
});
