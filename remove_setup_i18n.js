const fs = require('fs')
const files = ['zh', 'en', 'ja', 'ko']
const keysToRemove = ['configWizardDesc', 'rerunSetup', 'confirmRerunSetup', 'confirmRerunSetupDesc']
files.forEach(lang => {
  const p = `mingtang/src/i18n/locales/${lang}.json`
  const j = JSON.parse(fs.readFileSync(p, 'utf8'))
  let removed = 0
  if (j.settings?.other) {
    keysToRemove.forEach(k => {
      if (j.settings.other[k] !== undefined) {
        delete j.settings.other[k]
        removed++
      }
    })
  }
  if (j.setupPage) {
    delete j.setupPage
    removed++
  }
  fs.writeFileSync(p, JSON.stringify(j, null, 2) + '\n', 'utf8')
  console.log(`${lang}: removed ${removed} keys`)
})
