import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createWorker} from '../sites/reef-lab/worker.mjs';

const JPEG_B64 = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDAooor0D5s/9k=';
const image = {mimeType: 'image/jpeg', data: JPEG_B64, camera: 'tool', time: 12.5};

const body = {id: 'd-1', observation: {phase: 'inspect', eligible: true}, allowedActions: ['proceed', 'abort']};
const request = (value = body, headers = {}) => new Request('https://reef.example/api/lab/decision', {
  method: 'POST', headers: {'content-type': 'application/json', ...headers}, body: JSON.stringify(value),
});
const provider = (decision = 'proceed') => Response.json({status: 'completed', id: 'int-1',
  steps: [{type: 'model_output', content: [{type: 'text', text: JSON.stringify({decision, reason: 'Eligibility verified.'})}]}], usage: {total_tokens: 100}});

test('health and missing key never request Gemini', async () => {
  const worker = createWorker({transport: () => { throw new Error('Must not call'); }});
  const health = await worker.fetch(new Request('https://reef.example/api/lab/health'));
  const status = await health.json();
  assert.equal(status.geminiConfigured, false);
  assert.equal(status.input, 'robot_camera_and_sonar_telemetry');
  assert.equal((await worker.fetch(request())).status, 503);
});

test('current REST schema and validated decision evidence', async () => {
  const worker = createWorker({transport: async (url, options) => {
    assert.equal(url, 'https://generativelanguage.googleapis.com/v1beta/interactions');
    assert.equal(options.headers['x-goog-api-key'], 'test-only');
    const payload = JSON.parse(options.body);
    assert.equal(payload.store, false);
    assert.deepEqual(payload.response_format.schema.properties.decision.enum, body.allowedActions);
    return provider();
  }});
  const response = await worker.fetch(request(), {GEMINI_API_KEY: 'test-only'});
  assert.equal(response.status, 200);
  const decision = await response.json();
  assert.equal(decision.source, 'gemini');
  assert.equal(decision.id, body.id);
  assert.equal(decision.usage.total_tokens, 100);
  assert.equal((await worker.fetch(request(), {GEMINI_API_KEY: 'test-only'})).status, 429);
});

test('rejects cross-origin, malformed, oversized and nonfinite input', async () => {
  const worker = createWorker();
  assert.equal((await worker.fetch(request(body, {origin: 'https://attacker.example'}))).status, 403);
  assert.equal((await worker.fetch(request({...body, allowedActions: ['move']}))).status, 400);
  assert.equal((await worker.fetch(request({...body, observation: {note: 'x'.repeat(33000)}}))).status, 400);
  const invalid = new Request('https://reef.example/api/lab/decision', {method: 'POST', headers: {'content-type': 'application/json'}, body: '{"id":"d","observation":{"a":1e999},"allowedActions":["abort"]}'});
  assert.equal((await worker.fetch(invalid)).status, 400);
});

test('provider failures and disallowed decisions stay errors', async () => {
  for (const transport of [async () => provider('retry'), async () => {throw new Error('secret leaked');}]) {
    const response = await createWorker({transport}).fetch(request(), {GEMINI_API_KEY: 'test-only'});
    assert.equal(response.status, 502);
    assert.ok(!(await response.text()).includes('secret leaked'));
  }
});

test('static fallback uses ASSETS binding', async () => {
  const response = await createWorker().fetch(new Request('https://reef.example/lab/'), {
    ASSETS: {fetch: async request => new Response(new URL(request.url).pathname)},
  });
  assert.equal(await response.text(), '/lab/');
});

test('sends rendered camera image and sonar as multimodal input with hash evidence', async () => {
  const observation = {phase: 'inspect', sonar: {valid: true, ranges: [0.5, 1.2]}};
  const worker = createWorker({transport: async (_url, options) => {
    const payload = JSON.parse(options.body);
    assert.deepEqual(payload.input[1], {type: 'image', mime_type: 'image/jpeg', data: JPEG_B64});
    const telemetry = JSON.parse(payload.input[0].text);
    assert.deepEqual(telemetry.observation, observation);
    assert.deepEqual(telemetry.cameraFrame, {camera: 'tool', time: 12.5, width: 2, height: 2});
    assert.ok(!payload.input[0].text.includes(JPEG_B64));
    assert.match(payload.system_instruction, /health metadata remain authoritative/);
    return provider();
  }});
  const response = await worker.fetch(request({...body, observation, image}), {GEMINI_API_KEY: 'test-only'});
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.inputImageSha256, createHash('sha256').update(Buffer.from(JPEG_B64, 'base64')).digest('hex'));
  assert.equal(result.inputCamera, 'tool');
  assert.equal(result.inputImageTime, 12.5);
  assert.equal(result.inputMode, 'robot_camera_and_sonar_telemetry');
  assert.ok(!JSON.stringify(result).includes(JPEG_B64));
});

test('rejects invalid JPEG base64, image metadata and image size before provider call', async () => {
  const hugeDimensions = Buffer.from(JPEG_B64, 'base64');
  const sof = hugeDimensions.indexOf(Buffer.from([255, 192]));
  hugeDimensions.writeUInt16BE(769, sof + 5);
  const cases = [null, {...image, time: -1}, {...image, time: true}, {...image, camera: 'orbit'},
    {...image, mimeType: 'image/png'}, {...image, data: JPEG_B64 + '\n'},
    {...image, data: `data:image/jpeg;base64,${JPEG_B64}`},
    {...image, data: hugeDimensions.toString('base64')},
    {...image, data: Buffer.from(JPEG_B64, 'base64').subarray(0, -2).toString('base64')},
    {...image, data: Buffer.alloc(512 * 1024 + 1).toString('base64')}, {...image, extra: true}];
  const worker = createWorker({transport: () => {throw new Error('Should not call provider');}});
  for (const invalid of cases) {
    const response = await worker.fetch(request({...body, image: invalid}), {GEMINI_API_KEY: 'test-only'});
    assert.equal(response.status, 400);
  }
});

test('camera allowance does not expand the structured telemetry limit', async () => {
  const worker = createWorker();
  const response = await worker.fetch(request({...body, image, observation: {large: 'x'.repeat(32768)}}));
  assert.equal(response.status, 400);
});
