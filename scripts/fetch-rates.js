#!/usr/bin/env node
/**
 * Mortgage Rate Fetcher v3
 * 
 * Extracts structured rate data from:
 * - Bankrate's __NEXT_DATA__ JSON (national lenders)
 * - PatelCo Credit Union (local CU rates)
 * - Star One Credit Union (local CU rates)
 * - National averages (from page text)
 * - ARM rates from dedicated ARM page
 * 
 * Outputs:
 *   data/rates-YYYY-MM-DD.json  (full historical record)
 *   site/data/latest.json       (for public website)
 *   data/last-change-report.txt (if rates changed vs yesterday)
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const SITE_DATA_DIR = path.join(ROOT, 'site', 'data');

[DATA_DIR, SITE_DATA_DIR].forEach(d => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

// Your loan profile
const MY_PROFILE = {
  currentRate: 5.8,
  loanType: "5/1 ARM",
  location: "Milpitas, CA 95035",
  propertyType: "Single-family detached",
};

function fetch(url) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
      }
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetch(res.headers.location).then(resolve).catch(reject);
      }
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => resolve({ body, statusCode: res.statusCode }));
    });
    req.on('error', reject);
    req.setTimeout(20000, () => { req.destroy(); reject(new Error('timeout: ' + url)); });
    req.end();
  });
}

function extractNextData(body) {
  const m = body.match(/__NEXT_DATA__"[^>]*>([^<]+)</i);
  if (!m) throw new Error('No __NEXT_DATA__ found');
  return JSON.parse(m[1]);
}

function parseProducts(data) {
  const query = data.props?.pageProps?.dehydratedState?.queries?.[0];
  if (!query) return { lenders: [], queryKey: null };
  
  const d = query.state?.data;
  if (!d) return { lenders: [], queryKey: query.queryKey };
  
  const institutions = d.institutions || {};
  const terms = d.terms || {};
  
  const lenders = (d.products || []).map(p => {
    const inst = institutions[p.institutionId] || {};
    const off = p.offering || {};
    const dims = p.dimensions || {};
    
    return {
      lender: inst.name || inst.displayName || 'Unknown',
      lenderId: p.institutionId,
      logo: inst.logo || null,
      product: p.name || p.displayName || '',
      productTypeId: p.productTypeId,
      rate: off.rate || null,
      apr: off.apr || null,
      points: off.points || null,
      monthlyPayment: off.estimatedPayment || off.principalAndInterestPayment || null,
      upFrontCosts: off.upFrontCosts || null,
      fiveYearCost: off.fiveYearCost || null,
      eightYearCost: off.eightYearCost || null,
      interestType: dims.interestType || null,
      loanSize: dims.size || null,
      isFHA: dims.isFha || false,
      isVA: dims.isVa || false,
      lockDays: p.eligibility?.lockDays || null,
    };
  }).filter(l => l.rate !== null);
  
  return { lenders, queryKey: query.queryKey };
}

// Parse national averages from page text
// Strips HTML tags first for reliable regex matching
function parseNationalAverages(body) {
  // Strip HTML tags and normalize whitespace
  const text = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  const rates = {};
  
  // National averages: "30-year fixed ... 6.58%"
  const m30 = text.match(/30.year.fixed[^]{0,300}?(\d+\.\d{2,3})%/i);
  if (m30) rates['30_year_fixed'] = parseFloat(m30[1]);
  
  const m15 = text.match(/15.year.fixed[^]{0,300}?(\d+\.\d{2,3})%/i);
  if (m15) rates['15_year_fixed'] = parseFloat(m15[1]);
  
  // ARM national average: "the national average 5/1 ARM APR is 6.18%"
  const armMatch = text.match(/national average 5.1.ARM APR is\s+([\d.]+)%/i);
  if (armMatch) rates['5_1_arm_apr'] = parseFloat(armMatch[1]);
  
  const arm101Match = text.match(/10.1.ARM APR is\s+([\d.]+)%/i);
  if (arm101Match) rates['10_1_arm_apr'] = parseFloat(arm101Match[1]);
  
  // Weekly trend block: "5/1 ARM 6.20% 15 year fixed 5.89% 30 year fixed 6.52%"
  const weekly = text.match(/5.1.ARM\s+([\d.]+)%\s+15.year.fixed\s+([\d.]+)%\s+30.year.fixed\s+([\d.]+)%/i);
  if (weekly) {
    rates.weekly_trend = {
      arm_5_1: parseFloat(weekly[1]),
      fixed_15: parseFloat(weekly[2]),
      fixed_30: parseFloat(weekly[3]),
    };
  }
  
  // Top daily offer
  const topOffer = text.match(/top offers on Bankrate:\s+([\d.]+)%/i);
  if (topOffer) rates.top_daily_offer = parseFloat(topOffer[1]);
  
  return rates;
}

// Parse PatelCo Credit Union rates from their mortgage page HTML
function parsePatelCo(body) {
  const text = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  const fixed = [];
  const arm = [];

  // Fixed-rate products: "30-Year Fixed $50,000 to $832,750 6.625% 6.710%"
  const fixedRegex = /(\d+)-Year Fixed(?:\s+(?:High Balance|Jumbo))?\s+\$[\d,]+\s+to\s+\$[\d,]+\s+(\d+\.\d{2,4})%\s+(\d+\.\d{2,4})%/gi;
  const seen = new Set();
  let m;
  while ((m = fixedRegex.exec(text)) !== null) {
    const key = `${m[1]}yr-${m[2]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    fixed.push({
      term: `${m[1]}-Year Fixed`,
      rate: parseFloat(m[2]),
      apr: parseFloat(m[3]),
    });
  }

  // ARM products: "5/1 30-Year Adjustable 6.125% 6.279%"
  const armRegex = /(\d+\/\d+)\s+30-Year Adjustable(?:\s+Jumbo)?\s+\$[\d,]+\s+to\s+\$[\d,]+\s+(\d+\.\d{2,4})%\s+(\d+\.\d{2,4})%/gi;
  const seenArm = new Set();
  while ((m = armRegex.exec(text)) !== null) {
    const key = `${m[1]}-${m[2]}`;
    if (seenArm.has(key)) continue;
    seenArm.add(key);
    arm.push({
      term: `${m[1]} ARM`,
      rate: parseFloat(m[2]),
      apr: parseFloat(m[3]),
    });
  }

  return {
    name: 'PatelCo Credit Union',
    url: 'https://www.patelco.org/credit-cards-and-loans/home-loans/mortgage',
    fixed,
    arm,
  };
}

// Parse Star One Credit Union rates from their mortgage page HTML
function parseStarOne(body) {
  const text = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  const fixed = [];
  const arm = [];

  // Fixed rates: "N-year mortgage at X.XXX% (Y.YYY% APR"
  const fixedRegex = /(\d+)-year mortgage at (\d+\.\d{2,4})%\s*\((\d+\.\d{2,4})%\s*APR/gi;
  const seen = new Set();
  let m;
  while ((m = fixedRegex.exec(text)) !== null) {
    const key = `${m[1]}yr`;
    if (seen.has(key)) continue;
    seen.add(key);
    fixed.push({
      term: `${m[1]}-Year Fixed`,
      rate: parseFloat(m[2]),
      apr: parseFloat(m[3]),
    });
  }

  // ARM rates: "N-Year Fixed-to-Adjustable-Rate Mortgage ... is X.XXX% (Y.YYY% APR for conforming"
  const armRegex = /(\d+)-Year Fixed-to-Adjustable-Rate Mortgage.*?is (\d+\.\d{2,4})%\s*\((\d+\.\d{2,4})%\s*APR for conforming/gi;
  const seenArm = new Set();
  while ((m = armRegex.exec(text)) !== null) {
    const key = `${m[1]}yr`;
    if (seenArm.has(key)) continue;
    seenArm.add(key);
    arm.push({
      term: `${m[1]}/1 ARM`,
      rate: parseFloat(m[2]),
      apr: parseFloat(m[3]),
    });
  }

  return {
    name: 'Star One Credit Union',
    url: 'https://www.starone.org/rates/mortgage-rates',
    fixed,
    arm,
  };
}

async function main() {
  const today = new Date().toISOString().split('T')[0];
  const now = new Date().toISOString();
  console.log(`[${now}] Fetching mortgage rates for ${today}...`);

  const result = {
    date: today,
    fetchedAt: now,
    profile: MY_PROFILE,
    nationalAverages: {},
    lenderOffers: [],
    armRates: {},
    summary: {},
  };

  // === Fetch Bankrate main page ===
  try {
    console.log('→ Bankrate main rates page...');
    const res = await fetch('https://www.bankrate.com/mortgages/mortgage-rates/');
    const nextData = extractNextData(res.body);
    const { lenders, queryKey } = parseProducts(nextData);
    result.lenderOffers = lenders;
    result.queryParams = queryKey;
    console.log(`  ✓ ${lenders.length} lender offers extracted`);

    const natAvg = parseNationalAverages(res.body);
    result.nationalAverages = { ...result.nationalAverages, ...natAvg };
    console.log('  ✓ National averages:', JSON.stringify(natAvg));
  } catch (e) {
    console.error('  ✗ Bankrate main failed:', e.message);
    result.errors = result.errors || [];
    result.errors.push({ source: 'bankrate_main', error: e.message });
  }

  // === Fetch Bankrate ARM page ===
  try {
    console.log('→ Bankrate ARM rates page...');
    const res = await fetch('https://www.bankrate.com/mortgages/5-1-arm-rates/');
    const armData = parseNationalAverages(res.body);
    result.armRates = armData;
    
    // Try to get ARM lender offers too
    try {
      const nextData = extractNextData(res.body);
      const { lenders: armLenders } = parseProducts(nextData);
      if (armLenders.length) {
        result.armLenderOffers = armLenders;
        console.log(`  ✓ ${armLenders.length} ARM lender offers extracted`);
      }
    } catch (e) {
      // ARM page might not have structured data
    }
    
    console.log('  ✓ ARM rates:', JSON.stringify(armData));
  } catch (e) {
    console.error('  ✗ Bankrate ARM failed:', e.message);
  }

  // === Fetch PatelCo Credit Union rates ===
  try {
    console.log('→ PatelCo Credit Union rates...');
    const res = await fetch('https://www.patelco.org/credit-cards-and-loans/home-loans/mortgage');
    result.creditUnions = result.creditUnions || {};
    result.creditUnions.patelco = parsePatelCo(res.body);
    console.log(`  ✓ PatelCo: ${result.creditUnions.patelco.fixed.length} fixed, ${result.creditUnions.patelco.arm.length} ARM rates`);
  } catch (e) {
    console.error('  ✗ PatelCo failed:', e.message);
    result.errors = result.errors || [];
    result.errors.push({ source: 'patelco', error: e.message });
  }

  // === Fetch Star One Credit Union rates ===
  try {
    console.log('→ Star One Credit Union rates...');
    const res = await fetch('https://www.starone.org/rates/mortgage-rates');
    result.creditUnions = result.creditUnions || {};
    result.creditUnions.starone = parseStarOne(res.body);
    console.log(`  ✓ Star One: ${result.creditUnions.starone.fixed.length} fixed, ${result.creditUnions.starone.arm.length} ARM rates`);
  } catch (e) {
    console.error('  ✗ Star One failed:', e.message);
    result.errors = result.errors || [];
    result.errors.push({ source: 'starone', error: e.message });
  }

  // === Build summary ===
  // Merge national averages with ARM-specific data
  const na = { ...(result.armRates || {}), ...(result.nationalAverages || {}) };
  const wt = na.weekly_trend || {};
  
  result.summary = {
    '30_year_fixed': wt.fixed_30 || na['30_year_fixed'] || null,
    '15_year_fixed': wt.fixed_15 || na['15_year_fixed'] || null,
    '5_1_arm': wt.arm_5_1 || na['5_1_arm_apr'] || null,
    '10_1_arm': na['10_1_arm_apr'] || null,
    'top_daily_30yr_offer': na.top_daily_offer || null,
    'best_30yr_lender_rate': result.lenderOffers.length
      ? Math.min(...result.lenderOffers.filter(l => l.product?.includes('30')).map(l => l.rate))
      : null,
    'my_rate': MY_PROFILE.currentRate,
    'my_loan_type': MY_PROFILE.loanType,
  };

  // Compare to your rate
  const marketARM = result.summary['5_1_arm'];
  if (marketARM) {
    const diff = marketARM - MY_PROFILE.currentRate;
    result.summary.vs_my_rate = {
      market_5_1_arm: marketARM,
      my_rate: MY_PROFILE.currentRate,
      difference: parseFloat(diff.toFixed(3)),
      i_save_or_lose_per_month: null, // would need loan amount
      assessment: diff > 0.5 ? '🌟 Your rate is EXCELLENT — well below market'
                 : diff > 0.25 ? '✅ Your rate is BETTER than market'
                 : diff > 0.05 ? '🟢 Your rate is slightly better than market'
                 : diff > -0.05 ? '🟡 Market is about equal to your rate'
                 : diff > -0.25 ? '🟠 Market is slightly better — watch for refinance'
                 : '🔴 Market is BETTER — consider refinancing',
    };
  }

  // === Save files ===
  const dayFile = path.join(DATA_DIR, `rates-${today}.json`);
  fs.writeFileSync(dayFile, JSON.stringify(result, null, 2));
  console.log(`\nSaved: ${dayFile}`);

  // Latest for website
  const latestFile = path.join(SITE_DATA_DIR, 'latest.json');
  fs.writeFileSync(latestFile, JSON.stringify(result, null, 2));
  console.log(`Saved: ${latestFile}`);

  // === Detect changes vs yesterday ===
  const yesterdayDate = new Date(Date.now() - 86400000).toISOString().split('T')[0];
  const yFile = path.join(DATA_DIR, `rates-${yesterdayDate}.json`);
  const changes = [];

  if (fs.existsSync(yFile)) {
    const yData = JSON.parse(fs.readFileSync(yFile, 'utf8'));
    for (const key of ['30_year_fixed', '15_year_fixed', '5_1_arm', '10_1_arm', 'top_daily_30yr_offer', 'best_30yr_lender_rate']) {
      const t = result.summary[key];
      const y = yData.summary?.[key];
      if (t != null && y != null && Math.abs(t - y) >= 0.005) {
        const arrow = t > y ? '📈' : '📉';
        const delta = (t - y).toFixed(3);
        changes.push(`${arrow} ${key.replace(/_/g, ' ')}: ${y.toFixed(3)}% → ${t.toFixed(3)}% (${delta > 0 ? '+' : ''}${delta}%)`);
      }
    }
  }

  // Print summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 MORTGAGE RATE DASHBOARD — ' + today);
  console.log('='.repeat(60));
  
  const s = result.summary;
  const fmt = v => v != null ? v.toFixed(2) + '%' : 'N/A';
  
  console.log(`30-Year Fixed:      ${fmt(s['30_year_fixed'])}`);
  console.log(`15-Year Fixed:      ${fmt(s['15_year_fixed'])}`);
  console.log(`5/1 ARM:            ${fmt(s['5_1_arm'])}`);
  console.log(`10/1 ARM:           ${fmt(s['10_1_arm'])}`);
  console.log(`Top 30yr Daily:     ${fmt(s['top_daily_30yr_offer'])}`);
  console.log(`Best Lender 30yr:   ${fmt(s['best_30yr_lender_rate'])}`);
  console.log('-'.repeat(60));
  console.log(`Your Rate (5/1 ARM): ${MY_PROFILE.currentRate}%`);
  
  if (s.vs_my_rate) {
    console.log(`Market 5/1 ARM:     ${s.vs_my_rate.market_5_1_arm.toFixed(2)}%`);
    console.log(`Difference:         ${s.vs_my_rate.difference > 0 ? '+' : ''}${s.vs_my_rate.difference}%`);
    console.log(`Status:             ${s.vs_my_rate.assessment}`);
  }

  if (result.lenderOffers.length) {
    console.log('\n--- Top Lender Offers ---');
    const byRate = [...result.lenderOffers].sort((a, b) => (a.rate || 99) - (b.rate || 99));
    byRate.slice(0, 5).forEach((l, i) => {
      console.log(`  ${i+1}. ${l.lender} — ${l.product}: ${l.rate}% (APR ${l.apr}%, ${l.points} pts, $${Math.round(l.monthlyPayment || 0)}/mo)`);
    });
  }

  // Print credit union rates
  if (result.creditUnions) {
    console.log('\n--- Local Credit Union Rates ---');
    for (const [key, cu] of Object.entries(result.creditUnions)) {
      console.log(`\n  ${cu.name}:`);
      for (const f of cu.fixed) {
        const marker = f.term === '30-Year Fixed' ? ' ←' : '';
        console.log(`    ${f.term}: ${f.rate}% (APR ${f.apr}%)${marker}`);
      }
      for (const a of cu.arm) {
        const marker = a.term === '5/1 ARM' || a.term === '5/1 ARM' ? ' ←' : '';
        console.log(`    ${a.term}: ${a.rate}% (APR ${a.apr}%)${marker}`);
      }
    }
  }

  if (changes.length) {
    console.log('\n🔔 RATE CHANGES SINCE YESTERDAY:');
    changes.forEach(c => console.log('  ' + c));
    
    const report = `📊 MORTGAGE RATE CHANGES — ${today}\n\n${changes.join('\n')}\n\n` +
      `Your ${MY_PROFILE.loanType}: ${MY_PROFILE.currentRate}%\n` +
      (s.vs_my_rate ? `Market 5/1 ARM: ${s.vs_my_rate.market_5_1_arm.toFixed(2)}% — ${s.vs_my_rate.assessment}` : '');
    fs.writeFileSync(path.join(DATA_DIR, 'last-change-report.txt'), report);
    console.log('\n⚠️ Change alert saved.');
  } else {
    const rptFile = path.join(DATA_DIR, 'last-change-report.txt');
    if (fs.existsSync(rptFile)) fs.unlinkSync(rptFile);
    console.log('\n✓ No significant changes since yesterday.');
  }

  console.log('='.repeat(60));
  return result;
}

main().catch(err => {
  console.error('FATAL:', err);
  process.exit(1);
});
