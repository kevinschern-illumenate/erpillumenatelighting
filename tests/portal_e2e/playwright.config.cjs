const {defineConfig} = require('@playwright/test');
module.exports = defineConfig({
    testDir: '.', testMatch: '*.spec.cjs', fullyParallel: false, workers: 1, retries: 0,
    timeout: 60000, outputDir: 'artifacts',
    reporter: [['list'], ['json', {outputFile:'artifacts/results.json'}]],
    use: {baseURL:process.env.B2B_E2E_URL, trace:'off', screenshot:'only-on-failure', video:'off'},
    projects:[{name:'desktop', use:{viewport:{width:1440,height:900}}},
        {name:'tablet', use:{viewport:{width:768,height:1024}}},
        {name:'mobile', use:{viewport:{width:390,height:844}}}]
});
