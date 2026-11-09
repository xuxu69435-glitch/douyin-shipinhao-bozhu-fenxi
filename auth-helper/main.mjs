// Private stdio bridge. Account credentials never leave the trusted processes.
import { createInterface } from 'node:readline';
import { createChatGPT } from './vendor/siwc-local/src/index.ts';

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
const pending = new Map();
let serial = 0;
let started = false;
const send = value => process.stdout.write(JSON.stringify(value) + '\n');
function rpc(type, value) {
  const id = ++serial;
  return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); send({ type, id, value }); });
}
lines.on('line', async line => {
  if (started) {
    const message = JSON.parse(line);
    const waiter = pending.get(message.id);
    if (waiter) {
      pending.delete(message.id);
      message.error ? waiter.reject(new Error('Local credential operation failed')) : waiter.resolve(message.value);
    }
    return;
  }
  try {
    const message = JSON.parse(line);
    started = true;
    const client = createChatGPT({
      appName: 'Douyin Analyst', appId: 'com.douyinanalyst.desktop',
      redirectPort: 0, storageDir: message.storageDir, sendHostId: true,
      credentialEncryption: {
        id: 'windows-dpapi-v1', isAvailable: () => process.platform === 'win32',
        encrypt: async text => Buffer.from(await rpc('encrypt', Buffer.from(text, 'utf8').toString('base64')), 'base64'),
        decrypt: async bytes => Buffer.from(await rpc('decrypt', Buffer.from(bytes).toString('base64')), 'base64').toString('utf8'),
      },
      openBrowser: async url => { await rpc('browser', url); },
    });
    let result;
    const args = message.args ?? {};
    switch (message.op) {
      case 'status': result = await client.getSession(); break;
      case 'sign-in': result = await client.signIn({ signal: AbortSignal.timeout(240_000) }); break;
      case 'disconnect': await client.disconnect(); result = await client.getSession(); break;
      case 'models': result = await client.listModels({ signal: AbortSignal.timeout(30_000) }); break;
      case 'generate': {
        if (typeof args.model !== 'string' || typeof args.content !== 'string' || args.content.length > 70_000)
          throw new Error('Invalid inference request');
        let length = 0;
        result = await client.streamResponse({
          model: args.model, instructions: args.instructions,
          input: [{ role: 'user', content: args.content }], signal: AbortSignal.timeout(90_000),
          onDelta: delta => { length += delta.length; if (length > 32_768) throw new Error('Output character limit exceeded'); },
        });
        break;
      }
      default: throw new Error('Unknown bridge operation');
    }
    send({ type: 'result', value: result });
  } catch (error) {
    // Unknown exceptions may contain credentials or submitted text. Expose only codes.
    send({ type: 'error', code: typeof error?.code === 'string' ? error.code : 'bridge_operation_failed',
      retryable: error?.retryable === true });
  } finally {
    if (started && !pending.size) { lines.close(); process.stdin.unref(); }
  }
});
