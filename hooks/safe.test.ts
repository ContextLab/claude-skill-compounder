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

// ---- one test per kind of secret ----

const SECRET = 'hunter2hunter2'
const gone = (text: string) => {
  const out = redact(text)
  expect(out.includes(SECRET)).toBe(false)
  expect(out.includes('<redacted>')).toBe(true)
  return out
}

test('a bare secret name is an assignment too: TOKEN=, PASSWORD=, SECRET=, KEY=, *_KEY=, password= in any case', async () => {
  for (const name of ['TOKEN', 'PASSWORD', 'SECRET', 'KEY', 'API_KEY', 'OPENAI_API_KEY', 'password', 'Password', 'token', 'secret', 'db_password', 'PGPASSWORD']) {
    expect(redact(`${name}=${SECRET} ./run.sh`)).toBe(`${name}=<redacted> ./run.sh`)
    expect(redact(`export ${name}="${SECRET} two" && make`)).toBe(`export ${name}=<redacted> && make`)
  }
  expect(redact(`curl 'https://x.test/a?password=${SECRET}&page=2'`).includes(SECRET)).toBe(false)
  expect(redact('PROFILE=dev COUNT=3 ./build.sh')).toBe('PROFILE=dev COUNT=3 ./build.sh')
})

test('curl -u, mysql -p, docker login -p and sshpass -p lose the password', async () => {
  expect(gone(`curl -u admin:${SECRET} https://x.test/api`)).toBe('curl -u <redacted> https://x.test/api')
  expect(gone(`curl -s --user "admin:${SECRET}" https://x.test`)).toBe('curl -s --user <redacted> https://x.test')
  expect(gone(`mysql -u root -p${SECRET} shop -e 'select 1'`)).toBe("mysql -u root -p<redacted> shop -e 'select 1'")
  expect(gone(`mysqldump -h db -p${SECRET} shop > dump.sql`)).toBe('mysqldump -h db -p<redacted> shop > dump.sql')
  expect(gone(`docker login -u me -p ${SECRET} registry.test`)).toBe('docker login -u me -p <redacted> registry.test')
  expect(gone(`sshpass -p ${SECRET} ssh host`)).toBe('sshpass -p <redacted> ssh host')
  expect(redact('mkdir -p build/out && cp -p a b')).toBe('mkdir -p build/out && cp -p a b')
  expect(redact('mysql -p shop')).toBe('mysql -p shop')
})

test('an Authorization header of any scheme and an X-Api-Key header are masked', async () => {
  expect(gone(`curl -H "Authorization: Bearer ${SECRET}" https://x.test`)).toBe('curl -H "Authorization: Bearer <redacted>" https://x.test')
  expect(gone(`curl -H 'Authorization: Basic ${SECRET}'`)).toBe("curl -H 'Authorization: Basic <redacted>'")
  expect(gone(`curl -H "authorization: ${SECRET}" https://x.test`)).toBe('curl -H "authorization: <redacted>" https://x.test')
  expect(gone(`curl -H 'X-Api-Key: ${SECRET}' https://x.test`)).toBe("curl -H 'X-Api-Key: <redacted>' https://x.test")
  expect(gone(`curl -H "x-api-key:${SECRET}"`)).toBe('curl -H "x-api-key:<redacted>"')
  expect(gone(`curl -H 'X-Auth-Token: ${SECRET}'`)).toBe("curl -H 'X-Auth-Token: <redacted>'")
})

test('JSON api_key, token and password values are masked, plain and inside a shell string', async () => {
  expect(gone(`{"api_key": "${SECRET}", "page": 2}`)).toBe('{"api_key": "<redacted>", "page": 2}')
  expect(gone(`{"token":"${SECRET}"}`)).toBe('{"token":"<redacted>"}')
  expect(gone(`{"user":"jo","password":"${SECRET}"}`)).toBe('{"user":"jo","password":"<redacted>"}')
  expect(gone(`{"access_token":"${SECRET}"}`)).toBe('{"access_token":"<redacted>"}')
  expect(gone(`WebFetch {"headers":{"Authorization":"Bearer ${SECRET}"}}`).includes('"Authorization":"')).toBe(true)
  expect(gone(`curl -d "{\\"password\\": \\"${SECRET}\\"}" https://x.test`)).toBe('curl -d "{\\"password\\": \\"<redacted>\\"}" https://x.test')
  expect(gone(`requests.post(u, json={'token': '${SECRET}'})`)).toBe("requests.post(u, json={'token': '<redacted>'})")
  expect(redact('{"max_tokens": 400, "name": "x"}')).toBe('{"max_tokens": 400, "name": "x"}')
})

test('a PEM block is masked whole, and to the end when it was cut', async () => {
  const pem = '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA7hunter\nabc123\n-----END RSA PRIVATE KEY-----'
  expect(redact(`cat > k.pem <<EOF\n${pem}\nEOF`)).toBe('cat > k.pem <<EOF\n<redacted>\nEOF')
  expect(redact('-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk')).toBe('<redacted>')
  expect(redact('-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY----- after')).toBe('<redacted> after')
})

test('each common token shape is masked: ghp_, sk-, xoxb-/xoxa-/xoxp-, AKIA', async () => {
  for (const shape of [
    'ghp_abcdefghijklmnopqrstuvwxyz0123456789',
    'sk-ant-api03-abcdefghijklmnop',
    'sk-proj-abcdefghijklmnopqrstuv',
    'xoxb-123456789012-abcdefghijkl',
    'xoxa-123456789012-abcdefghijkl',
    'xoxp-123456789012-abcdefghijkl',
    'AKIAIOSFODNN7EXAMPLE',
    'github_pat_11ABCDEFG0abcdefghijkl',
  ]) {
    expect(redact(`deploy ${shape} now`)).toBe('deploy <redacted> now')
  }
  expect(redact('the task-runner and risk-register docs')).toBe('the task-runner and risk-register docs')
})
