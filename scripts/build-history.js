#!/usr/bin/env node
/**
 * Build history.json from all daily rate files
 * Run after fetch-rates.js to update the website's chart data
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const SITE_DATA_DIR = path.join(__dirname, '..', 'site', 'data');

const files = fs.readdirSync(DATA_DIR)
  .filter(f => f.match(/^rates-\d{4}-\d{2}-\d{2}\.json$/))
  .sort();

const history = files.map(f => {
  const data = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf8'));
  return {
    date: data.date,
    summary: {
      '30_year_fixed': data.summary?.['30_year_fixed'] || null,
      '15_year_fixed': data.summary?.['15_year_fixed'] || null,
      '5_1_arm': data.summary?.['5_1_arm'] || null,
      '10_1_arm': data.summary?.['10_1_arm'] || null,
      'best_30yr_lender_rate': data.summary?.['best_30yr_lender_rate'] || null,
    },
  };
});

// Keep last 90 days
const trimmed = history.slice(-90);

const outFile = path.join(SITE_DATA_DIR, 'history.json');
fs.writeFileSync(outFile, JSON.stringify(trimmed, null, 2));
console.log(`History: ${trimmed.length} days written to ${outFile}`);
