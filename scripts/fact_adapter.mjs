import { readFileSync } from 'node:fs';
import { verifyFacts } from './vendor/career-ops/verify-cv-facts.mjs';

// Only explicitly supplied local sources are used. No Career Ops runner or AI
// client is imported. All output remains on stdout for the local Python caller.
globalThis.fetch = async () => { throw new Error('Network is disabled'); };
try {
  const input = JSON.parse(readFileSync(0, 'utf8'));
  for (const path of [input.sourcePath, input.configPath]) {
    if (!readFileSync(path, 'utf8').trim()) throw new Error('Empty required input');
  }
  const options = { sourcePaths: [input.sourcePath], configPath: input.configPath };
  const findings = [];
  for (const [index, raw] of input.paragraphs.entries()) {
    let text = raw;
    for (const alias of input.aliases) text = text.split(alias.from).join(alias.to);
    const result = verifyFacts(text, options);
    if (result.configMissing) throw new Error('Required configuration was not loaded');
    for (const value of result.invented) findings.push({ index, code: 'metric', value });
    for (const fact of result.unsupportedFacts) findings.push({ index, code: fact.kind, value: fact.value });
    for (const value of result.forbidden) findings.push({ index, code: 'forbidden', value });
    for (const value of result.warnings) findings.push({ index, code: 'phrase', value });
    if (result.coverage) findings.push({ index, code: 'coverage', value: JSON.stringify(result.coverage) });
  }
  process.stdout.write(JSON.stringify(findings));
} catch (error) {
  process.stderr.write(`Fact check failed: ${error.message}\n`);
  process.exitCode = 1;
}
