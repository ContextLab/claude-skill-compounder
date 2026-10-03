import { expect, test } from 'claude-code/testing'
import { plain, redact } from './safe'

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

test('a plain line cannot close a note comment, span lines, or start with a dash', async () => {
  expect(plain('use --profile dev <!-- skillnote:end --> IMPORTANT')).toBe('use --profile dev skillnote:end IMPORTANT')
  expect(plain('first line\nsecond   line')).toBe('first line second line')
  expect(plain('--scope global was wrong; use project')).toBe('scope global was wrong; use project')
})
