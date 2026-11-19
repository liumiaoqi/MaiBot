#!/usr/bin/env node
/**
 * WebUI 契约层 CLI
 *
 * 子命令：snapshot | generate | check | report
 *
 * 退出码契约（命令级不可混用）：
 * - snapshot / generate / report 失败 → 1
 * - check 一切判定结果（consistent/stale/handEdited/missing/skipped）→ 0
 * - 任意子命令参数非法 / I/O 异常 → 2
 */

/* global console, process */

import { execFileSync } from 'node:child_process'
import { mkdir, readFile, writeFile, unlink } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { Buffer } from 'node:buffer'
import path from 'node:path'

import {
  buildGaps,
  diffOperationSets,
  extractOperations,
  groupByPrefix,
  summarizeCoverage,
} from './lib/contract-model.mjs'
import { applyBanner, computeArtifactSha256, isHandEdited, parseBanner } from './lib/banner.mjs'
import { scanHandWrittenPaths } from './lib/path-scan.mjs'
import { resolveSource, SOURCE_MODES } from './lib/source.mjs'
import { renderCoverageReport, stableStringify } from './lib/report.mjs'

const ROOT = path.resolve(import.meta.dirname, '../..')
const DEFAULT_OUT_DIR = path.join(ROOT, 'openapi')
const DEFAULT_ARTIFACT = path.join(ROOT, 'src', 'lib', 'contract', 'api-schema.d.ts')
const GENERATOR_BIN = path.join(ROOT, 'node_modules', 'openapi-typescript', 'bin', 'cli.js')

function parseArgs(argv) {
  const args = { _: [] }
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index]
    if (token === '--') continue
    if (!token.startsWith('--')) {
      args._.push(token)
      continue
    }
    const body = token.slice(2)
    const equalsIndex = body.indexOf('=')
    if (equalsIndex >= 0) {
      args[body.slice(0, equalsIndex)] = body.slice(equalsIndex + 1)
      continue
    }
    const next = argv[index + 1]
    if (next !== undefined && !next.startsWith('--')) {
      args[body] = next
      index += 1
      continue
    }
    args[body] = true
  }
  return args
}

function resolvePaths(args) {
  const outDir = typeof args['out-dir'] === 'string' ? path.resolve(ROOT, args['out-dir']) : DEFAULT_OUT_DIR
  return {
    outDir,
    snapshotPath:
      typeof args.snapshot === 'string'
        ? path.resolve(ROOT, args.snapshot)
        : path.join(outDir, 'openapi.json'),
    metaPath: path.join(outDir, 'meta.json'),
    reportPath: path.join(outDir, 'coverage-report.md'),
    gapsPath: path.join(outDir, 'gaps.json'),
    baselinePath: path.join(outDir, 'path-baseline.json'),
    lastCheckPath: path.join(outDir, 'last-check.json'),
    lastGeneratePath: path.join(outDir, 'last-generate.json'),
    artifactPath: typeof args.artifact === 'string' ? path.resolve(ROOT, args.artifact) : DEFAULT_ARTIFACT,
  }
}

async function readJsonIfExists(filePath) {
  if (!existsSync(filePath)) return null
  try {
    return JSON.parse(await readFile(filePath, 'utf8'))
  } catch {
    return null
  }
}

async function readGeneratorVersion() {
  const packageJson = JSON.parse(await readFile(path.join(ROOT, 'package.json'), 'utf8'))
  return packageJson.devDependencies?.['openapi-typescript'] ?? 'unknown'
}

function collectShapeGaps(operations) {
  const noShape = []
  const wideObject = []
  for (const operation of operations) {
    const responses = operation.operation.responses ?? {}
    const successStatuses = Object.keys(responses).filter((status) => /^2\d\d$/.test(status))
    if (successStatuses.length === 0) continue
    const withSchema = successStatuses.find((status) => {
      const schema = responses[status]?.content?.['application/json']?.schema
      return schema && typeof schema === 'object' && Object.keys(schema).length > 0
    })
    const label = `${operation.method.toUpperCase()} ${operation.path}`
    if (!withSchema) {
      noShape.push(label)
      continue
    }
    const schema = responses[withSchema].content['application/json'].schema
    if (schema.type === 'object' && !schema.properties) wideObject.push(label)
  }
  return { noShape, wideObject }
}

function buildMeta(sourceResult, schema, previousMeta) {
  const operations = extractOperations(schema)
  const schemaCount = Object.keys(schema.components?.schemas ?? {}).length
  const warnings = []
  if (previousMeta && Number.isFinite(previousMeta.operationCount)) {
    const dropRatio = 1 - operations.length / previousMeta.operationCount
    if (dropRatio > 0.3) {
      warnings.push(
        `规模骤降：操作数 ${previousMeta.operationCount} → ${operations.length}（下降 ${Math.round(dropRatio * 100)}%）`,
      )
    }
  }
  return {
    sourceKind: sourceResult.sourceKind,
    sourceId: sourceResult.sourceId,
    fetchedAt: sourceResult.fetchedAt,
    openapiVersion: schema.openapi,
    pathCount: Object.keys(schema.paths ?? {}).length,
    operationCount: operations.length,
    schemaCount,
    normalizedSha256: sourceResult.normalizedSha256,
    byteLength: sourceResult.byteLength,
    warnings,
  }
}

async function writeJson(filePath, value) {
  await writeFile(filePath, stableStringify(value), 'utf8')
}

async function writeReportArtifacts(paths, schema, meta, previousMeta) {
  const operations = extractOperations(schema)
  const coverage = summarizeCoverage(operations)
  const groups = groupByPrefix(operations)
  const gaps = buildGaps(operations)
  const baseline = scanHandWrittenPaths({ rootDir: path.join(ROOT, 'src', 'lib') })
  const shapeGaps = collectShapeGaps(operations)

  if (previousMeta) {
    const previousSchema = await readJsonIfExists(path.join(path.dirname(paths.snapshotPath), 'previous-openapi.json'))
    if (previousSchema) {
      meta.diff = diffOperationSets(extractOperations(previousSchema), operations)
    }
  }

  await mkdir(paths.outDir, { recursive: true })
  await writeJson(paths.metaPath, meta)
  await writeJson(paths.gapsPath, gaps)
  await writeJson(paths.baselinePath, baseline)
  await writeFile(
    paths.reportPath,
    renderCoverageReport({
      meta,
      coverage,
      groups,
      gaps,
      baseline,
      noShapeOperations: shapeGaps.noShape,
      wideObjectOperations: shapeGaps.wideObject,
    }),
    'utf8',
  )

  console.log(`[contract] 来源=${meta.sourceId}`)
  console.log(`[contract] normalized-sha256=${meta.normalizedSha256.slice(0, 16)}`)
  console.log(`[contract] paths=${meta.pathCount} operations=${meta.operationCount} schemas=${meta.schemaCount}`)
  console.log(`[contract] 覆盖：有响应模型 ${coverage.withResponseSchema}/${coverage.total}，缺口 ${gaps.length}`)
  console.log(`[contract] 路径基线：${baseline.occurrences} 处 / ${baseline.uniqueCount} unique`)
  for (const warning of meta.warnings) console.log(`[contract] ⚠️ ${warning}`)
  return { coverage, groups, gaps, baseline, shapeGaps }
}

function normalizeSourceId(sourceResult, paths) {
  if (sourceResult.sourceKind === 'snapshot') {
    return `snapshot:${path.relative(ROOT, paths.snapshotPath).replaceAll('\\', '/')}`
  }
  return sourceResult.sourceId
}

async function runSnapshot(args, paths) {
  const previousMeta = await readJsonIfExists(paths.metaPath)
  const source = await resolveSource({
    mode: typeof args.source === 'string' ? args.source : 'auto',
    url: typeof args.url === 'string' ? args.url : undefined,
    snapshotPath: paths.snapshotPath,
    snapshotFetchedAt: previousMeta?.fetchedAt,
    timeoutMs: Number.isFinite(Number(args.timeout)) ? Number(args.timeout) : undefined,
  })
  if (!source.ok) {
    console.error(`[contract] 取源失败：${source.message}`)
    return 1
  }
  source.sourceId = normalizeSourceId(source, paths)
  const meta = buildMeta(source, source.schema, previousMeta)
  await mkdir(paths.outDir, { recursive: true })
  await writeFile(paths.snapshotPath, source.text, 'utf8')
  await writeReportArtifacts(paths, source.schema, meta, previousMeta)
  return 0
}

async function runReport(args, paths) {
  const snapshotText = await readFile(paths.snapshotPath, 'utf8')
  const schema = JSON.parse(snapshotText)
  const previousMeta = await readJsonIfExists(paths.metaPath)
  const meta = previousMeta ?? {
    sourceKind: 'snapshot',
    sourceId: 'snapshot:openapi/openapi.json',
    fetchedAt: 'unknown',
    openapiVersion: schema.openapi,
    pathCount: Object.keys(schema.paths ?? {}).length,
    operationCount: extractOperations(schema).length,
    schemaCount: Object.keys(schema.components?.schemas ?? {}).length,
    normalizedSha256: '',
    byteLength: Buffer.byteLength(snapshotText, 'utf8'),
    warnings: [],
  }
  const { createHash } = await import('node:crypto')
  meta.normalizedSha256 = createHash('sha256').update(snapshotText, 'utf8').digest('hex')
  await writeReportArtifacts(paths, schema, meta, previousMeta)
  return 0
}

function runGenerator(snapshotPath, temporaryOutput) {
  execFileSync(process.execPath, [GENERATOR_BIN, snapshotPath, '--output', temporaryOutput], {
    cwd: ROOT,
    stdio: 'pipe',
    encoding: 'utf8',
  })
}

async function runGenerate(args, paths) {
  const previousMeta = await readJsonIfExists(paths.metaPath)
  let source
  try {
    source = await resolveSource({
      mode: typeof args.source === 'string' ? args.source : 'http',
      url: typeof args.url === 'string' ? args.url : undefined,
      snapshotPath: paths.snapshotPath,
      snapshotFetchedAt: previousMeta?.fetchedAt,
      timeoutMs: Number.isFinite(Number(args.timeout)) ? Number(args.timeout) : undefined,
    })
  } catch (error) {
    await recordGenerateFailure(paths, {
      failureKind: 'internal-error',
      message: error instanceof Error ? error.message : String(error),
      attemptedLocation: [],
    })
    return 1
  }

  if (!source.ok) {
    const failureKind =
      source.kind === 'unreachable'
        ? 'unreachable'
        : source.kind === 'invalid-json' || source.kind === 'missing-openapi' || source.kind === 'missing-paths'
          ? 'invalid-contract'
          : source.kind === 'unsupported-openapi'
            ? 'unsupported-version'
            : 'no-source'
    await recordGenerateFailure(paths, {
      failureKind,
      message: source.message,
      rawSnippet: source.rawSnippet ?? '',
      attemptedLocation: source.attempts?.map((attempt) => attempt.attempted) ?? [],
    })
    return 1
  }

  source.sourceId = normalizeSourceId(source, paths)

  const temporaryOutput = `${paths.artifactPath}.tmp`
  try {
    await mkdir(paths.outDir, { recursive: true })
    await mkdir(path.dirname(paths.artifactPath), { recursive: true })
    await writeFile(paths.snapshotPath, source.text, 'utf8')
    runGenerator(paths.snapshotPath, temporaryOutput)
    const body = await readFile(temporaryOutput, 'utf8')
    const generatorVersion = await readGeneratorVersion()
    const schema = source.schema
    const banner = {
      generator: 'openapi-typescript',
      generatorVersion,
      source: source.sourceId,
      fetchedAt: source.fetchedAt,
      normalizedSha256: source.normalizedSha256,
      pathCount: Object.keys(schema.paths ?? {}).length,
      operationCount: extractOperations(schema).length,
      schemaCount: Object.keys(schema.components?.schemas ?? {}).length,
      artifactSha256: computeArtifactSha256(body),
    }
    await writeFile(paths.artifactPath, applyBanner(body, banner), 'utf8')
    await unlink(temporaryOutput)

    const meta = buildMeta(source, schema, previousMeta)
    await writeReportArtifacts(paths, schema, meta, previousMeta)
    await writeJson(paths.lastGeneratePath, {
      verdict: 'success',
      sourceKind: source.sourceKind,
      attemptedLocation: [source.sourceId],
      failureKind: 'none',
      message: '',
      occurredAt: new Date().toISOString(),
    })
    console.log(`[contract] 产物已生成：${path.relative(ROOT, paths.artifactPath)}`)
    return 0
  } catch (error) {
    try {
      await unlink(temporaryOutput)
    } catch {
      // 临时文件可能未创建
    }
    await recordGenerateFailure(paths, {
      failureKind: 'generator-failed',
      message: error instanceof Error ? error.message : String(error),
      attemptedLocation: [source.sourceId],
    })
    return 1
  }
}

async function recordGenerateFailure(paths, detail) {
  const payload = {
    verdict: 'failed',
    sourceKind: 'unknown',
    attemptedLocation: detail.attemptedLocation ?? [],
    failureKind: detail.failureKind ?? 'unknown',
    message: detail.message ?? '',
    rawSnippet: detail.rawSnippet ?? '',
    occurredAt: new Date().toISOString(),
  }
  try {
    await mkdir(paths.outDir, { recursive: true })
    await writeJson(paths.lastGeneratePath, payload)
  } catch (error) {
    console.error(`[contract] 写入 last-generate.json 失败：${error instanceof Error ? error.message : String(error)}`)
  }
  console.error(`[contract] 生成失败（${payload.failureKind}）：${payload.message}`)
}

async function runCheck(args, paths) {
  const artifactExists = existsSync(paths.artifactPath)
  let verdict
  let message

  if (!artifactExists) {
    verdict = 'missing'
    message = `产物不存在：${path.relative(ROOT, paths.artifactPath)}`
  } else {
    const artifactText = await readFile(paths.artifactPath, 'utf8')
    if (isHandEdited(artifactText)) {
      verdict = 'handEdited'
      message = '产物正文与头注 artifact-sha256 不一致（疑似手改或头注损坏）'
    } else {
      const parsed = parseBanner(artifactText)
      const source = await resolveSource({
        mode: typeof args.source === 'string' ? args.source : 'auto',
        url: typeof args.url === 'string' ? args.url : undefined,
        snapshotPath: paths.snapshotPath,
        timeoutMs: Number.isFinite(Number(args.timeout)) ? Number(args.timeout) : undefined,
      })
      if (!source.ok) {
        verdict = 'skipped'
        message = `契约来源不可用，已跳过一致性判定：${source.message}`
      } else if (parsed.fields.normalizedSha256 === source.normalizedSha256) {
        verdict = 'consistent'
        message = '产物与当前契约一致'
      } else {
        verdict = 'stale'
        message = `产物基于旧契约（产物 ${parsed.fields.normalizedSha256.slice(0, 16)} ≠ 当前 ${source.normalizedSha256.slice(0, 16)}）`
      }
    }
  }

  const payload = {
    verdict,
    message,
    artifact: path.relative(ROOT, paths.artifactPath),
    checkedAt: new Date().toISOString(),
  }
  await mkdir(paths.outDir, { recursive: true })
  await writeJson(paths.lastCheckPath, payload)
  console.log(`[contract] check：${verdict} — ${message}`)
  return 0
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const subcommand = args._[0]
  const paths = resolvePaths(args)

  if (!subcommand || !['snapshot', 'generate', 'check', 'report'].includes(subcommand)) {
    console.error(`[contract] 未知子命令：${subcommand ?? '(空)'}`)
    return 2
  }
  if (typeof args.source === 'string' && !SOURCE_MODES.includes(args.source)) {
    console.error(`[contract] 非法的 --source：${args.source}`)
    return 2
  }

  try {
    if (subcommand === 'snapshot') return await runSnapshot(args, paths)
    if (subcommand === 'generate') return await runGenerate(args, paths)
    if (subcommand === 'check') return await runCheck(args, paths)
    return await runReport(args, paths)
  } catch (error) {
    console.error(`[contract] 内部错误：${error instanceof Error ? error.message : String(error)}`)
    return 2
  }
}

const exitCode = await main()
process.exitCode = exitCode