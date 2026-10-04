import { expect, test } from 'claude-code/testing'
import { excerpt, oneLine, redact } from './safe'

test('an assignment whose name says secret is masked, and an ordinary one is not', async () => {
  expect(redact('DEPLOY_TOKEN=sk-live-9f8e7d6c5b4a3210FAKE ./build.sh')).toBe('DEPLOY_TOKEN=<redacted> ./build.sh')
  expect(redact('export AWS_SECRET_ACCESS_KEY="abc def" && make')).toBe('export AWS_SECRET_ACCESS_KEY=<redacted> && make')
  expect(redact('BUILD_ENV=dev ./build.sh')).toBe('BUILD_ENV=dev ./build.sh')
})

test('a flag whose name says secret is masked', async () => {
  expect(redact('deploy --token abc123def456 --env prod')).toBe('deploy --token <redacted> --env prod')
  expect(redact('login --password=hunter2hunter2')).toBe('login --password=<redacted>')
})

test('an authorization header and credentials in a URL are masked', async () => {
  expect(redact("curl -H 'Authorization: Bearer abcdefghijklmnop' https://x.test")).toBe("curl -H 'Authorization: Bearer <redacted>' https://x.test")
  expect(redact('git clone https://jo:s3cretpw@github.com/a/b.git')).toBe('git clone https://<redacted>@github.com/a/b.git')
})

test('well-known token shapes are masked wherever they sit', async () => {
  expect(redact('echo ghp_abcdefghijklmnopqrstuvwxyz0123')).toBe('echo <redacted>')
  expect(redact('use AKIAABCDEFGHIJKLMNOP now')).toBe('use <redacted> now')
})

test('one line is masked, flattened and cut with a mark', async () => {
  expect(oneLine('first\n  second\tthird', 80)).toBe('first second third')
  expect(oneLine('API_KEY=abcdef123456 run', 80)).toBe('API_KEY=<redacted> run')
  const cut = oneLine('x'.repeat(50), 10)
  expect(cut.length).toBe(10)
  expect(cut.endsWith('…')).toBe(true)
})

test('a short text is passed whole and a long one keeps head and tail around a mark', async () => {
  expect(excerpt('abc', 10, 10)).toBe('abc')
  const cut = excerpt('a'.repeat(50) + 'b'.repeat(50), 10, 5)
  expect(cut.startsWith('aaaaaaaaaa\n[... 85 characters omitted here ...]\n')).toBe(true)
  expect(cut.endsWith('bbbbb')).toBe(true)
})
