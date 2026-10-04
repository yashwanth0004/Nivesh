document.addEventListener('DOMContentLoaded', () => {

    // ════════════════════════════════════════════════════
    //  SCENARIO DEFINITIONS
    // ════════════════════════════════════════════════════
    const SCENARIOS = {
        normal: {
            label: 'Normal Market',
            desc: '🟢 <strong>Normal Market</strong> — Steady long-term growth with typical daily ups and downs. Like a well-managed kirana store that grows slowly year after year.',
            analogy: 'Like a fixed deposit in a bank that slowly but surely grows — small daily changes, but generally upward over years.',
            params: (day, total, type) => {
                const base = type === 'stock' ? { mu: 0.10, sig: 0.20 } : { mu: 0.05, sig: 0.03 };
                return { ...base, leverage: 1, crashChance: 1/10000, crashMin: 0.03, crashMax: 0.05 };
            }
        },
        crash: {
            label: 'Market Crash',
            desc: '📉 <strong>Market Crash</strong> — Simulates a 2008 or 2020-style crisis. The market drops 40–60% before slowly recovering. See if your strategy can survive!',
            analogy: 'Like when the COVID lockdown hit — all shops closed, prices fell drastically. But things slowly recovered afterward.',
            params: (day, total, type) => {
                const pct = day / total;
                const base = type === 'stock' ? { mu: 0.10, sig: 0.20 } : { mu: 0.05, sig: 0.03 };
                if (pct < 0.30) return { ...base, leverage: 1, crashChance: 1/10000, crashMin: 0.03, crashMax: 0.05 };
                if (pct < 0.60) return { mu: -0.45, sig: 0.35, leverage: 1, crashChance: 1/800, crashMin: 0.06, crashMax: 0.15 };
                return { mu: 0.20, sig: 0.25, leverage: 1, crashChance: 1/10000, crashMin: 0.03, crashMax: 0.05 };
            }
        },
        highvol: {
            label: 'High Volatility',
            desc: '⚡ <strong>High Volatility</strong> — Very dramatic daily swings. Like a cricket match — things can change completely in one over. High risk, high potential reward.',
            analogy: 'Like vegetable prices in the sabzi mandi that can double one week and halve the next depending on rain and supply.',
            params: (day, total, type) => {
                const base = type === 'stock' ? { mu: 0.09, sig: 0.50 } : { mu: 0.04, sig: 0.10 };
                return { ...base, leverage: 1, crashChance: 1/3000, crashMin: 0.05, crashMax: 0.12 };
            }
        },
        fraud: {
            label: 'Fraud / Scam Scenario',
            desc: '🚨 <strong>Fraud / Scam</strong> — This simulates investing in a fraudulent scheme (Ponzi/chit fund fraud). It looks great initially, then collapses suddenly. Learn to recognise this pattern!',
            analogy: 'Like a chit-fund scheme that promised 30% monthly returns — your money seemed to grow for a few months, then the organiser disappeared with everything.',
            params: (day, total, type) => {
                return { mu: 0.12, sig: 0.08, leverage: 1, crashChance: 0, crashMin: 0, crashMax: 0 };
            }
        },
        leverage: {
            label: 'Leverage (2× Borrowed Money)',
            desc: '⚠️ <strong>Leverage (2×)</strong> — You borrow money to invest double your capital. Profits and LOSSES are both doubled. This is very dangerous for new investors!',
            analogy: 'Like borrowing ₹10,000 from a moneylender to invest ₹20,000. If you gain 20%, great. But if you lose 20%, you still owe the lender AND lost your own money.',
            params: (day, total, type) => {
                const base = type === 'stock' ? { mu: 0.10, sig: 0.20 } : { mu: 0.05, sig: 0.03 };
                return { ...base, leverage: 2, crashChance: 1/10000, crashMin: 0.03, crashMax: 0.05 };
            }
        }
    };

    let currentScenario = 'normal';

    // Render scenario cards
    const scenarioCards = document.querySelectorAll('.scenario-card');
    const scenarioDescEl = document.getElementById('scenario-desc');

    function selectScenario(s) {
        currentScenario = s;
        scenarioCards.forEach(c => c.classList.toggle('active', c.dataset.scenario === s));
        scenarioDescEl.innerHTML = SCENARIOS[s].desc;
        const fraudBox = document.getElementById('fraud-box');
        if (fraudBox) fraudBox.classList.toggle('hidden', s !== 'fraud');
    }

    scenarioCards.forEach(c => c.addEventListener('click', () => selectScenario(c.dataset.scenario)));
    selectScenario('normal');

    // ════════════════════════════════════════════════════
    //  LANGUAGE TOGGLE (Bilingual hints)
    // ════════════════════════════════════════════════════
    let hiMode = false;
    document.getElementById('btn-lang').addEventListener('click', () => {
        hiMode = !hiMode;
        document.querySelectorAll('.hi').forEach(el => {
            el.style.fontWeight = hiMode ? '600' : 'normal';
            el.style.color = hiMode ? '#1e40af' : '';
        });
        document.getElementById('btn-lang').textContent = hiMode ? '🇬🇧 English' : '🇮🇳 हिंदी';
        // Show analogies on assets in Hindi mode
        document.querySelectorAll('.asset-analogy').forEach(el => {
            el.style.display = hiMode ? 'block' : 'none';
        });
    });

    // ════════════════════════════════════════════════════
    //  MODE TOGGLE
    // ════════════════════════════════════════════════════
    const comb2Card = document.getElementById('comb-2-card');
    const modeRadios = document.getElementsByName('simMode');
    const totalCapitalInput = document.getElementById('total-capital');

    function getMode() { return document.querySelector('input[name="simMode"]:checked').value; }

    function updateMode() {
        const isCompare = getMode() === 'compare';
        comb2Card.classList.toggle('hidden', !isCompare);
        document.querySelectorAll('.col-c2').forEach(el => el.classList.toggle('hidden', !isCompare));
        const s2 = document.getElementById('summary-c2');
        const cb = document.getElementById('chart-b-box');
        if (s2) s2.classList.toggle('hidden', !isCompare);
        if (cb) cb.classList.toggle('hidden', !isCompare);
    }
    modeRadios.forEach(r => r.addEventListener('change', updateMode));

    // ════════════════════════════════════════════════════
    //  CHART EXPAND
    // ════════════════════════════════════════════════════
    window.toggleExpand = function(id) {
        const box = document.getElementById(id);
        box.classList.toggle('fullscreen');
        box.querySelector('.btn-expand').textContent = box.classList.contains('fullscreen') ? '✖ Close' : '⛶ Expand';
        setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
    };

    // ════════════════════════════════════════════════════
    //  ASSET MANAGEMENT
    // ════════════════════════════════════════════════════
    let combinationA = [], combinationB = [];
    let assetCounter = 1;
    const c1Assets = document.getElementById('c1-assets');
    const c2Assets = document.getElementById('c2-assets');

    function addAsset(container, arr, overrides = {}) {
        if (arr.length >= 20) { alert('Max 20 assets per combination.'); return null; }

        const defaults = { type: 'stock', price: 100, mode: 'lumpsum', amount: 1000 };
        const data = { id: Date.now() + Math.random(), ...defaults, ...overrides };
        arr.push(data);

        const assetItem = document.getElementById('asset-template').content.cloneNode(true).querySelector('.asset-item');
        assetItem.querySelector('.asset-title').textContent = `Virtual Co. ${assetCounter++}`;

        const selType   = assetItem.querySelector('.asset-type');
        const inpPrice  = assetItem.querySelector('.asset-price');
        const selMode   = assetItem.querySelector('.inv-mode');
        const inpAmount = assetItem.querySelector('.inv-amount');
        const badge     = assetItem.querySelector('.risk-badge');
        const analogyEl = assetItem.querySelector('.asset-analogy');
        const dynamicLabel = assetItem.querySelector('.dynamic-inv-label');
        const costValue    = assetItem.querySelector('.cost-value');

        function syncBadge() {
            const isStock = data.type === 'stock';
            badge.textContent = isStock ? '⚡ High Risk' : '🏦 Low Risk';
            badge.className = 'risk-badge ' + (isStock ? 'high' : 'low');
            analogyEl.textContent = isStock
                ? '📌 Like buying shares of a company — value can rise or fall sharply'
                : '📌 Like lending money to government — safe, slow, steady returns';
        }

        function updateAssetUI() {
            if (data.mode === 'lumpsum') {
                dynamicLabel.innerHTML = 'Quantity <span class="hi">(मात्रा)</span>';
                const cost = data.amount * data.price;
                costValue.innerHTML = Math.round(cost).toLocaleString('en-IN');
            } else {
                dynamicLabel.innerHTML = 'Monthly Qty <span class="hi">(मासिक मात्रा)</span>';
                const totalDays = getTotalDays();
                const sipCount = Math.floor(totalDays / 30) + 1; // Includes Day 0 and every 30 days
                const cost = data.amount * data.price * sipCount;
                costValue.innerHTML = Math.round(cost).toLocaleString('en-IN') + ' <span style="font-size:0.75rem;font-weight:normal">(Est.)</span>';
            }
        }
        if (!window.assetUIUpdaters) window.assetUIUpdaters = [];
        window.assetUIUpdaters.push(updateAssetUI);

        selType.value   = data.type;
        inpPrice.value  = data.price;
        selMode.value   = data.mode;
        inpAmount.value = data.amount;
        syncBadge();
        updateAssetUI();

        selType.addEventListener('change',   e => { data.type = e.target.value; syncBadge(); updateTotals(); });
        selMode.addEventListener('change',   e => { data.mode = e.target.value; updateAssetUI(); updateTotals(); });
        inpPrice.addEventListener('input',   e => { 
            e.target.value = Math.abs(e.target.value);
            data.price = Math.max(+e.target.value, 0.01); 
            updateAssetUI(); 
            updateTotals(); 
        });
        inpAmount.addEventListener('input',  e => { 
            e.target.value = Math.abs(e.target.value);
            data.amount = Math.max(+e.target.value, 1); 
            updateAssetUI(); 
            updateTotals(); 
        });

        assetItem.querySelector('.btn-remove').addEventListener('click', () => {
            window.assetUIUpdaters = window.assetUIUpdaters.filter(fn => fn !== updateAssetUI);
            container.removeChild(assetItem);
            arr.splice(arr.findIndex(a => a.id === data.id), 1);
            updateTotals();
        });

        container.appendChild(assetItem);
        updateTotals();
        return data;
    }

    function getTotalDays() {
        const dur = +(document.getElementById('sim-duration').value || 1);
        const unit = document.getElementById('sim-duration-unit').value || 'years';
        if (unit === 'years') return Math.floor(dur * 365);
        if (unit === 'months') return Math.floor(dur * 30);
        if (unit === 'weeks') return Math.floor(dur * 7);
        return Math.floor(dur); // days
    }

    function updateTotals() {
        const cap = +totalCapitalInput.value || 0;
        const totalDays = getTotalDays();
        const sipCount = Math.floor(totalDays / 30) + 1;
        let hasError = false;

        [{ arr: combinationA, invId: 'c1-total-inv', leftId: 'c1-capital-left' },
         { arr: combinationB, invId: 'c2-total-inv', leftId: 'c2-capital-left' }]
        .forEach(({ arr, invId, leftId }) => {
            const tot = arr.reduce((s, a) => {
                if (a.mode === 'lumpsum') return s + (a.amount * a.price);
                else return s + (a.amount * a.price * sipCount);
            }, 0);
            
            document.getElementById(invId).textContent = Math.round(tot).toLocaleString('en-IN');
            const leftEl = document.getElementById(leftId);
            const left = cap - tot;
            
            if (left < 0) {
                leftEl.innerHTML = `Remaining: <span style="color:var(--danger); font-weight:bold;">₹${Math.round(left).toLocaleString('en-IN')} (Over Budget!)</span>`;
                leftEl.classList.add('capital-warning');
                hasError = true;
            } else {
                leftEl.textContent = `Remaining: ₹${Math.round(left).toLocaleString('en-IN')}`;
                leftEl.classList.remove('capital-warning');
            }
        });

        const btnRun = document.getElementById('btn-run-sim');
        btnRun.disabled = hasError;
        if (hasError) {
            btnRun.textContent = '⚠️ Reduce Investment (Over Budget)';
            btnRun.style.backgroundColor = '#9ca3af';
            btnRun.style.cursor = 'not-allowed';
        } else {
            btnRun.textContent = '▶ Run Simulation · सिमुलेशन चलाएं';
            btnRun.style.backgroundColor = '';
            btnRun.style.cursor = 'pointer';
        }
    }

    totalCapitalInput.addEventListener('input', e => { e.target.value = Math.abs(e.target.value); updateTotals(); });
    document.getElementById('sim-duration').addEventListener('input', e => {
        e.target.value = Math.abs(e.target.value);
        if (window.assetUIUpdaters) window.assetUIUpdaters.forEach(fn => fn());
        updateTotals();
    });
    document.getElementById('sim-duration-unit').addEventListener('change', () => {
        if (window.assetUIUpdaters) window.assetUIUpdaters.forEach(fn => fn());
        updateTotals();
    });
    document.getElementById('sim-iterations').addEventListener('input', e => {
        e.target.value = Math.abs(e.target.value);
    });
    
    document.getElementById('btn-add-c1').addEventListener('click', () => addAsset(c1Assets, combinationA));
    document.getElementById('btn-add-c2').addEventListener('click', () => addAsset(c2Assets, combinationB));

    // Initial defaults
    addAsset(c1Assets, combinationA, { type: 'stock', mode: 'lumpsum', amount: 50, price: 100 }); // 50 * 100 = 5000
    addAsset(c2Assets, combinationB, { type: 'bond',  mode: 'sip',     amount: 2,  price: 100 }); // 2 * 24 * 100 = 4800
    updateMode();

    // ════════════════════════════════════════════════════
    //  SIMULATION ENGINE
    // ════════════════════════════════════════════════════
    function randn() {
        let u = 0, v = 0;
        while (!u) u = Math.random();
        while (!v) v = Math.random();
        return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    }

    let simulationResults = null;
    let chartOverall = null, chartA = null, chartB = null;
    const iterationSelect = document.getElementById('chart-iteration-select');
    const resultsSection = document.getElementById('results-section');

    function runSimulation() {
        let iters = Math.min(Math.max(+document.getElementById('sim-iterations').value, 1), 100);
        document.getElementById('sim-iterations').value = iters;

        const isCompare = getMode() === 'compare';
        const totalDays = Math.max(1, getTotalDays());

        let candleDays, periodLabel;
        if (totalDays <= 60)         { candleDays = 1;   periodLabel = 'Day'; }
        else if (totalDays <= 180)   { candleDays = 7;   periodLabel = 'Week'; }
        else if (totalDays <= 1095)  { candleDays = 30;  periodLabel = 'Month'; }
        else                         { candleDays = 365; periodLabel = 'Year'; }

        const dt = 1 / 365;
        const sc = currentScenario;
        // Give each parallel universe its own broad market regime. This is a
        // zero-mean annual drift shock shared by both compared strategies, so
        // bull, base, and bear outcomes are possible without biasing the
        // long-run average return or giving either strategy a different market.
        const marketDriftShocks = Array.from({ length: iters }, () => randn());

        function simulateCombo(combo) {
            if (!combo.length) return null;
            const all = [];

            for (let iter = 0; iter < iters; iter++) {
                // For fraud: pick a random collapse day (30%-80% through)
                const fraudDay = sc === 'fraud'
                    ? Math.floor(totalDays * (0.30 + Math.random() * 0.50))
                    : -1;

                const daily = new Array(totalDays + 1).fill(0);
                let invested = 0;
                const states = combo.map(a => ({ ...a, price: +a.price, units: 0 }));

                for (let day = 0; day <= totalDays; day++) {
                    let val = 0;
                    for (const s of states) {
                        // Buy-in
                        if (day === 0 && s.mode === 'lumpsum') {
                            s.units += s.amount;
                            invested += s.amount * s.price;
                        } else if (s.mode === 'sip' && day % 30 === 0) { // SIP fires exactly every 30 days, including day 0
                            s.units += s.amount;
                            invested += s.amount * s.price;
                        }
                        val += s.units * s.price;

                        // Price evolution
                        if (day < totalDays) {
                            // Fraud collapse
                            if (sc === 'fraud' && day === fraudDay) {
                                const collapse = 0.70 + Math.random() * 0.20; // 70-90% loss
                                s.price = Math.max(0.01, s.price * (1 - collapse));
                            } else {
                                let p = SCENARIOS[sc].params(day, totalDays, s.type);
                                if (sc === 'normal' || sc === 'leverage') {
                                    const regimeVolatility = s.type === 'stock' ? 0.12 : 0.08;
                                    p = {
                                        ...p,
                                        mu: p.mu + marketDriftShocks[iter] * regimeVolatility
                                            - 0.5 * regimeVolatility * regimeVolatility * (totalDays / 365)
                                    };
                                }
                                const drift  = (p.mu - 0.5 * p.sig * p.sig) * dt;
                                const shock  = p.sig * Math.sqrt(dt) * randn();
                                const dailyRet = Math.exp(drift + shock) - 1;
                                // Leverage: multiply return
                                s.price = Math.max(0.001, s.price * (1 + p.leverage * dailyRet));
                                // Random crash
                                if (p.crashChance > 0 && Math.random() < p.crashChance) {
                                    const drop = p.crashMin + Math.random() * (p.crashMax - p.crashMin);
                                    s.price = Math.max(0.001, s.price * (1 - drop));
                                }
                            }
                        }
                    }
                    daily[day] = val;
                }

                // Build candles and periodic data
                const candles = [], periodic = [];
                for (let i = 0; i < totalDays; i += candleDays) {
                    const chunk = daily.slice(i, Math.min(i + candleDays, totalDays + 1));
                    if (!chunk.length) break;
                    const lbl = `${periodLabel} ${Math.floor(i / candleDays) + 1}`;
                    candles.push({
                        x: lbl,
                        y: [+chunk[0].toFixed(2), +Math.max(...chunk).toFixed(2),
                            +Math.min(...chunk).toFixed(2), +chunk.at(-1).toFixed(2)]
                    });
                    periodic.push({ period: lbl, val: chunk.at(-1) });
                }

                all.push({ finalValue: daily[totalDays], totalInvested: invested, candles, periodic });
            }
            return all;
        }

        const resA = simulateCombo(combinationA);
        const resB = isCompare ? simulateCombo(combinationB) : null;
        simulationResults = { resA, resB, isCompare };
        renderResults();
    }

    // ════════════════════════════════════════════════════
    //  RENDER RESULTS
    // ════════════════════════════════════════════════════
    const INR = v => '₹' + v.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    const PCT = v => v.toFixed(1) + '%';

    function stats(res) {
        if (!res) return null;
        const finals = res.map(r => r.finalValue);
        const invs   = res.map(r => r.totalInvested);
        const avgFin = finals.reduce((a,b) => a+b, 0) / finals.length;
        const avgInv = invs.reduce((a,b) => a+b, 0) / invs.length;
        const profitable = finals.filter((f, i) => f > invs[i]).length;
        const maxDrawdown = Math.min(...finals.map((f, i) => ((f - invs[i]) / invs[i]) * 100));
        return {
            avgFin, avgInv,
            ret: avgInv > 0 ? ((avgFin - avgInv) / avgInv) * 100 : 0,
            best: Math.max(...finals), worst: Math.min(...finals),
            profitPct: (profitable / finals.length * 100).toFixed(0),
            maxDrawdown,
            avgPath: (() => {
                const path = res[0].periodic.map(p => ({ x: p.period, y: 0 }));
                res.forEach(it => it.periodic.forEach((p, i) => path[i].y += p.val));
                path.forEach(p => p.y = +(p.y / res.length).toFixed(2));
                return path;
            })()
        };
    }

    function renderResults() {
        const { resA, resB, isCompare } = simulationResults;
        resultsSection.classList.remove('hidden');

        const sA = stats(resA);
        const sB = stats(resB);

        // Summary cards
        document.getElementById('c1-overall-val').textContent  = Math.round(sA.avgFin).toLocaleString('en-IN');
        document.getElementById('c1-tot-inv-res').textContent  = Math.round(sA.avgInv).toLocaleString('en-IN');
        document.getElementById('c1-return-perc').textContent  = PCT(sA.ret);
        document.getElementById('c1-profitable').textContent   = sA.profitPct;

        if (isCompare && sB) {
            document.getElementById('c2-overall-val').textContent  = Math.round(sB.avgFin).toLocaleString('en-IN');
            document.getElementById('c2-tot-inv-res').textContent  = Math.round(sB.avgInv).toLocaleString('en-IN');
            document.getElementById('c2-return-perc').textContent  = PCT(sB.ret);
            document.getElementById('c2-profitable').textContent   = sB.profitPct;
        }

        // Consequence panel
        document.getElementById('con-best-a').textContent  = INR(sA.best);
        document.getElementById('con-avg-a').textContent   = INR(sA.avgFin);
        document.getElementById('con-worst-a').textContent = INR(sA.worst);
        document.getElementById('con-maxloss-a').textContent = PCT(sA.maxDrawdown);

        if (isCompare && sB) {
            document.getElementById('con-best-b').textContent  = INR(sB.best);
            document.getElementById('con-avg-b').textContent   = INR(sB.avgFin);
            document.getElementById('con-worst-b').textContent = INR(sB.worst);
            document.getElementById('con-maxloss-b').textContent = PCT(sB.maxDrawdown);
        }

        // Guardrail-compliant conclusion (no tips, just observation)
        const concBox = document.getElementById('conclusion-box');
        if (isCompare && sB) {
            concBox.classList.remove('hidden');
            const rA = sA.ret, rB = sB.ret;
            let obs;
            if (rA > rB) {
                obs = `In this simulation under the <strong>${SCENARIOS[currentScenario].label}</strong> scenario, Combination A showed a higher average simulated return (${PCT(rA)}) compared to Combination B (${PCT(rB)}). Combination A was profitable in ${sA.profitPct}% of universes vs ${sB.profitPct}% for B.`;
            } else if (rB > rA) {
                obs = `In this simulation under the <strong>${SCENARIOS[currentScenario].label}</strong> scenario, Combination B showed a higher average simulated return (${PCT(rB)}) compared to Combination A (${PCT(rA)}). Combination B was profitable in ${sB.profitPct}% of universes vs ${sA.profitPct}% for A.`;
            } else {
                obs = `Both strategies performed similarly under the <strong>${SCENARIOS[currentScenario].label}</strong> scenario (~${PCT(rA)} return).`;
            }
            document.getElementById('conclusion-text').innerHTML = obs;
        } else { concBox.classList.add('hidden'); }

        // Fraud awareness
        document.getElementById('fraud-box').classList.toggle('hidden', currentScenario !== 'fraud');

        // Overall area chart
        if (chartOverall) chartOverall.destroy();
        const overallSeries = [{ name: 'Comb A (Avg)', data: sA.avgPath }];
        if (isCompare && sB) overallSeries.push({ name: 'Comb B (Avg)', data: sB.avgPath });
        chartOverall = new ApexCharts(document.querySelector('#chartOverall'), {
            chart: { type: 'area', height: '100%', toolbar: { show: false }, animations: { enabled: false } },
            dataLabels: { enabled: false },
            stroke: { curve: 'smooth', width: 2 },
            series: overallSeries,
            xaxis: { 
                type: 'category', 
                labels: { show: true, hideOverlappingLabels: true, trim: true },
                tooltip: { enabled: true }
            },
            colors: ['#1e40af', '#16a34a'],
            fill: { type: 'gradient', gradient: { opacityFrom: 0.35, opacityTo: 0.05 } },
            tooltip: { 
                x: { show: true },
                y: { formatter: v => '₹' + Math.round(v).toLocaleString('en-IN') } 
            }
        });
        chartOverall.render();

        // Iteration dropdown
        iterationSelect.innerHTML = '';
        resA.forEach((_, i) => {
            const o = document.createElement('option');
            o.value = i;
            o.textContent = `Iteration ${i + 1} — Final: ${INR(Math.round(resA[i].finalValue))}`;
            iterationSelect.appendChild(o);
        });
        iterationSelect.onchange = () => renderIteration(+iterationSelect.value);
        renderIteration(0);

        if (!tourActive) document.getElementById('overall-title').scrollIntoView({ behavior: 'smooth' });
    }

    function renderIteration(idx) {
        const { resA, resB, isCompare } = simulationResults;
        const itA = resA[idx], itB = resB ? resB[idx] : null;

        // Periodic table
        const tbody = document.getElementById('periodic-table-body');
        tbody.innerHTML = '';
        itA.periodic.forEach((p, i) => {
            const tr = document.createElement('tr');
            const cells = [
                p.period,
                '₹' + Math.round(p.val).toLocaleString('en-IN'),
                itB ? '₹' + Math.round(itB.periodic[i]?.val || 0).toLocaleString('en-IN') : '—'
            ];
            cells.forEach((txt, ci) => {
                const td = document.createElement('td');
                td.textContent = txt;
                if (ci === 2) td.classList.add('col-c2');
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });

        // Candlestick charts
        const opts = {
            chart: { type: 'candlestick', height: '100%', toolbar: { show: true, tools: { zoom: true, pan: true, reset: true } }, animations: { enabled: false } },
            xaxis: { 
                type: 'category', 
                labels: { show: true, hideOverlappingLabels: true, trim: true },
                tooltip: { enabled: true }
            },
            yaxis: { tooltip: { enabled: true }, labels: { formatter: v => '₹' + Math.round(v).toLocaleString('en-IN') } },
            tooltip: { x: { show: true } },
            plotOptions: { candlestick: { colors: { upward: '#16a34a', downward: '#dc2626' } } }
        };

        if (chartA) chartA.destroy();
        chartA = new ApexCharts(document.querySelector('#chartA'), { ...opts, series: [{ name: 'Comb A', data: itA.candles }] });
        chartA.render();

        if (isCompare && itB) {
            if (chartB) chartB.destroy();
            chartB = new ApexCharts(document.querySelector('#chartB'), { ...opts, series: [{ name: 'Comb B', data: itB.candles }] });
            chartB.render();
        }
    }

    document.getElementById('btn-run-sim').addEventListener('click', runSimulation);

    // ════════════════════════════════════════════════════
    //  INTERACTIVE TUTORIAL (12 Steps)
    // ════════════════════════════════════════════════════
    const tourPanel   = document.getElementById('tour-panel');
    const tourText    = document.getElementById('tour-text');
    const tourCounter = document.getElementById('tour-step-counter');
    const btnNext     = document.getElementById('btn-tour-next');
    const btnSkip     = document.getElementById('btn-tour-skip');
    let tourStep = 0, tourActive = false, cleanupFn = null;

    const activeTourLanguage = () => (document.documentElement.lang || 'en').toLowerCase();
    let tourTranslations = {};
    const tourTranslationsReady = fetch('/simulator_tour_translations.json?v=tour-i18n-20261004')
        .then(response => response.ok ? response.json() : {})
        .then(value => { tourTranslations = value || {}; })
        .catch(() => {});
    const tourUi = () => tourTranslations[activeTourLanguage()]?.ui || {
        step: 'Step', of: 'of', next: 'Next', finish: 'Finish', end: 'End Tutorial'
    };
    function updateTourControls() {
        const ui = tourUi();
        btnSkip.textContent = ui.end;
        if (!tourActive) {
            btnNext.textContent = ui.next;
            tourCounter.textContent = `${ui.step} 1 ${ui.of} 12`;
        }
    }
    tourTranslationsReady.then(updateTourControls);

    const tourSteps = [
        {
            id: 'step-header',
            title: 'Welcome to Nivesh Simulator!',
            body: `This is a <strong>free educational tool</strong> that helps you experience what investing feels like — without risking a single rupee.<br><br>
                   It is built for <strong>first-time investors, Tier-2/3 city users, and anyone who wants to understand markets before putting in real money.</strong><br><br>
                   <div class="analogy">Think of it like a "practice cricket net" — you can make mistakes here, learn, and then go bat in a real match.</div>
                   <em>⚠️ This tool never gives financial advice. It only shows simulated possibilities.</em>`
        },
        {
            id: 'step-scenario',
            title: 'Step 1 — Choose a Market Scenario',
            body: `Before simulating, pick what <strong>type of market you want to experience</strong>:<br><br>
                   <ul>
                     <li>🟢 <b>Normal</b> — Slow, steady growth. Low drama.</li>
                     <li>📉 <b>Market Crash</b> — 2008 / COVID-style severe drop and recovery.</li>
                     <li>⚡ <b>High Volatility</b> — Wild daily swings. High risk, high potential.</li>
                     <li>🚨 <b>Fraud/Scam</b> — See what a Ponzi scheme collapse looks like — and learn to recognise it!</li>
                     <li>⚠️ <b>Leverage</b> — Investing with borrowed money. Gains AND losses are doubled.</li>
                   </ul>
                   <em>👉 Task: Click the <b>🚨 Fraud/Scam</b> card to see how fraud looks, then switch back to Normal.</em>`,
            waitForClick: null // Free navigation step
        },
        {
            id: 'step-mode',
            title: 'Step 2 — Single or Compare?',
            body: `Choose how many strategies to test:<br><br>
                   • <b>Single Strategy</b> — Evaluate one portfolio on its own.<br>
                   • <b>Compare Two</b> — Run two different strategies side by side to see which holds up better under market conditions.<br><br>
                   <div class="analogy">Like comparing two different savings plans — one in a bank FD, one in mutual funds — to see which grew more.</div>
                   We have selected <strong>Compare</strong> mode for this tutorial.`
        },
        {
            id: 'step-global',
            title: 'Step 3 — Set Your Budget & Rules',
            body: `<ul>
                     <li><b>💰 Capital</b> — Your total available budget (e.g., ₹10,000). The simulator will never let you invest more than this without a warning.</li>
                     <li><b>📅 Duration</b> — How long into the future to project. You can now choose Days, Weeks, Months, or Years!</li>
                   <li><b>🔁 Iterations</b> — How many alternate market paths to run. Normal and leverage paths include shared bull/base/bear drift conditions. More paths make the estimate less sensitive to luck.</li>
                   </ul>
                   <em>👉 Task: Change <b>Total Capital</b> to ₹<b>50000</b> to continue.</em>`,
            waitForCondition: () => +totalCapitalInput.value === 50000,
            bindEl: 'total-capital', bindEvent: 'input'
        },
        {
            id: 'comb-1-card',
            title: 'Step 4 — Build Strategy A (Stock Lumpsum)',
            body: `This is your <strong>Combination A</strong> portfolio. We pre-set it as a ₹5,000 lumpsum investment (50 shares at ₹100 each) in a Virtual Stock.<br><br>
                   <ul>
                     <li><b>📈 Stock</b> — High risk, high potential return. Like shares of a company. Price can go up or down sharply.</li>
                     <li><b>💵 Lumpsum</b> — You invest the full ₹5,000 on Day 1. If the market drops on Day 2, your entire investment drops.</li>
                   </ul>
                   <div class="analogy">Like buying a bag of onions at ₹50/kg hoping to sell them later at ₹100/kg. The price might go up — or down to ₹20/kg!</div>`
        },
        {
            id: 'comb-2-card',
            title: 'Step 5 — Build Strategy B (Bond SIP)',
            body: `Combination B is a <strong>2 shares/month SIP in a Virtual Bond</strong>.<br><br>
                   <ul>
                     <li><b>🏦 Bond</b> — Low risk, stable return. Like lending money to the government. It grows slowly but reliably.</li>
                     <li><b>📆 SIP</b> — Systematic Investment Plan. You buy exactly 2 shares <i>every month</i>, so the actual rupee amount you spend changes as the market price goes up or down.</li>
                   </ul>
                   <div class="analogy">Like buying exactly 2 gold coins every month — the money you spend depends on the gold price that day!</div>
                   Notice the <strong>Remaining Capital</strong> counter below — it uses the initial price to estimate the budget.`
        },
        {
            id: 'step-run',
            title: 'Step 6 — Run the Simulation',
            body: `The simulator will now:<br><br>
                   1. Simulate <strong>daily price movements</strong> using a mathematical model (Geometric Brownian Motion — the same method used by financial analysts).<br>
                   2. Apply <strong>random market crashes</strong> (1-in-10,000 daily chance for a 3–5% drop).<br>
                   3. Repeat for <strong>20 alternate market universes</strong>.<br><br>
                   <em>👉 Task: Click the <b>"▶ Run Simulation"</b> button above.</em>`,
            waitForClick: 'btn-run-sim'
        },
        {
            id: 'overall-chart-box',
            title: 'Step 7 — Overall Expected Path',
            body: `This smooth <strong>area chart</strong> is the average across the selected market paths. It answers: <i>"On average, what could have happened under these assumptions?"</i><br><br>
                   • <b>Blue line</b> = Combination A (Stock)<br>
                   • <b>Green line</b> = Combination B (Bond SIP)<br><br>
                   <div class="analogy">Like asking 20 different people "what happened to your investment?" and averaging their answers to get a fair picture.</div>`
        },
        {
            id: 'summary-cards',
            title: 'Step 8 — Summary Cards & Outcome Frequency',
            body: `These cards show key numbers for each strategy:<br><br>
                   <ul>
                     <li><b>Avg Final Value</b> — What your portfolio was worth at the end, on average.</li>
                     <li><b>Total Invested</b> — Real money put in (lumpsum or SIP payments combined).</li>
                     <li><b>Simulated Return</b> — % profit or loss. Formula: <i>(Final − Invested) ÷ Invested × 100</i>.</li>
                     <li><b>Profitable in X% of iterations</b> — The share of simulated iterations where final value exceeded the amount invested. It can be below 80% or even 0%; it is a model outcome, not a real-world probability or a safety guarantee.</li>
                   </ul>
                   Compare this percentage with the average and worst-case results. A favorable average can still include many losing paths.`
        },
        {
            id: 'consequence-panel',
            title: 'Step 9 — Consequence Table',
            body: `This table shows the <strong>full range of outcomes</strong>:<br><br>
                   <ul>
                     <li><b>🏆 Best Case</b> — The single luckiest universe. Don't chase this alone!</li>
                     <li><b>📊 Average</b> — The most realistic expected outcome.</li>
                     <li><b>⚠️ Worst Case</b> — The unluckiest universe. Can you afford this loss?</li>
                     <li><b>📉 Max Loss %</b> — The biggest percentage drop seen. This is your downside risk.</li>
                   </ul>
                   <em>Always ask: "Can I survive the Worst Case?" before investing real money in any strategy.</em>`
        },
        {
            id: 'step-charts',
            title: 'Step 10 — Candlestick Charts',
            body: `Each bar (candle) = ONE time period (1 month here). Reading a candle:<br><br>
                   <ul>
                     <li><b>🟩 Green body</b> — That month's closing value was HIGHER than opening → profit that month.</li>
                     <li><b>🟥 Red body</b> — Closing was LOWER than opening → loss that month.</li>
                     <li><b>Top thin line (wick)</b> — The highest point touched that month. A sudden spike.</li>
                     <li><b>Bottom thin line</b> — The lowest crash during that month.</li>
                   </ul>
                   Use the <b>zoom toolbar</b> (top-right) to zoom in on any section. Click <b>⛶ Expand</b> for fullscreen.`
        },
        {
            id: 'step-table',
            title: 'Step 11 — Period-by-Period Table',
            body: `This table shows your portfolio value at the <strong>close of each period</strong> for the selected iteration.<br><br>
                   You can use this to identify:<br>
                   • When one strategy overtook the other<br>
                   • When a market crash hit and how long recovery took<br>
                   • Whether SIP or Lumpsum handled the crash better<br><br>
                   <em>👉 Task: Change the iteration dropdown above to <b>Iteration 2</b> to see a different market scenario.</em>`,
            waitForCondition: () => iterationSelect.value === '1',
            bindEl: 'chart-iteration-select', bindEvent: 'change'
        }
    ];

    async function startTour() {
        await tourTranslationsReady;
        updateTourControls();
        totalCapitalInput.value = 10000;
        document.getElementById('sim-duration').value = 2;
        document.getElementById('sim-duration-unit').value = 'years';
        document.getElementById('sim-iterations').value = 20;

        combinationA = []; combinationB = [];
        c1Assets.innerHTML = ''; c2Assets.innerHTML = '';

        addAsset(c1Assets, combinationA, { type: 'stock', mode: 'lumpsum', amount: 50, price: 100 });
        addAsset(c2Assets, combinationB, { type: 'bond',  mode: 'sip',     amount: 2,  price: 100 });

        document.querySelector('input[name="simMode"][value="compare"]').checked = true;
        selectScenario('normal');
        updateMode();
        updateTotals();

        tourActive = true; tourStep = 0;
        document.body.classList.add('tour-active');
        showStep();
    }

    function showStep() {
        if (!tourActive) return;
        if (tourStep >= tourSteps.length) { endTour(); return; }

        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
        if (cleanupFn) { cleanupFn(); cleanupFn = null; }

        const step = tourSteps[tourStep];
        const el = document.getElementById(step.id);
        if (el) { el.classList.add('tour-highlight'); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }

        const ui = tourUi();
        const localizedStep = tourTranslations[activeTourLanguage()]?.steps?.[step.id] || step;
        tourCounter.textContent = `${ui.step} ${tourStep + 1} ${ui.of} ${tourSteps.length}`;
        tourText.innerHTML = `<h3>${localizedStep.title}</h3>${localizedStep.body}`;
        btnNext.textContent = tourStep === tourSteps.length - 1 ? ui.finish : ui.next;
        btnNext.disabled = false;

        if (step.waitForClick) {
            btnNext.disabled = true;
            const target = document.getElementById(step.waitForClick);
            const handler = () => {
                target.removeEventListener('click', handler);
                setTimeout(() => { tourStep++; showStep(); }, 500);
            };
            target.addEventListener('click', handler);
            cleanupFn = () => target.removeEventListener('click', handler);

        } else if (step.waitForCondition) {
            btnNext.disabled = true;
            const target = document.getElementById(step.bindEl);
            const handler = () => {
                if (step.waitForCondition()) {
                    target.removeEventListener(step.bindEvent, handler);
                    cleanupFn = null;
                    setTimeout(() => { tourStep++; showStep(); }, 300);
                }
            };
            target.addEventListener(step.bindEvent, handler);
            cleanupFn = () => target.removeEventListener(step.bindEvent, handler);
        }
    }

    function endTour() {
        tourActive = false;
        if (cleanupFn) { cleanupFn(); cleanupFn = null; }
        document.body.classList.remove('tour-active');
        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
        tourStep = 0;
    }

    document.getElementById('btn-tutorial').addEventListener('click', startTour);
    btnSkip.addEventListener('click', endTour);
    btnNext.addEventListener('click', () => { if (!btnNext.disabled) { tourStep++; showStep(); } });

});
