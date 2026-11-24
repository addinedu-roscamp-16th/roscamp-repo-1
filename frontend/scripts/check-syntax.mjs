import { readdir, readFile } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { parse } from 'parse5'
import postcss from 'postcss'
import ts from 'typescript'

const scriptExtensions = new Set(['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts'])
const ignoredDirectories = new Set(['dist', 'coverage', 'node_modules'])
let checked = 0
let errors = 0

function report(file, message) {
  console.error(`${file}: ${message}`)
  errors++
}

async function check(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue
    const file = join(directory, entry.name)
    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) await check(file)
      continue
    }
    const extension = extname(file)
    if (!entry.isFile() || (extension !== '.html' && extension !== '.css' && !scriptExtensions.has(extension))) continue

    const source = await readFile(file, 'utf8')
    checked++
    if (extension === '.html') {
      parse(source, {
        onParseError(error) {
          report(file, `${error.startLine}:${error.startCol} ${error.code}`)
        },
      })
    } else if (extension === '.css') {
      try {
        postcss.parse(source, { from: file })
      } catch (error) {
        report(file, error.message)
      }
    } else {
      const program = ts.createProgram([file], { allowJs: true, noLib: true, noResolve: true, jsx: ts.JsxEmit.Preserve, target: ts.ScriptTarget.ESNext })
      for (const diagnostic of program.getSyntacticDiagnostics()) {
        if (diagnostic.category !== ts.DiagnosticCategory.Error) continue
        const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')
        const location = diagnostic.file?.getLineAndCharacterOfPosition(diagnostic.start ?? 0)
        report(file, location ? `${location.line + 1}:${location.character + 1} ${message}` : message)
      }
    }
  }
}

await check('.')
console.log(`Checked ${checked} web files. Syntax errors: ${errors}.`)
if (errors > 0) process.exitCode = 1
