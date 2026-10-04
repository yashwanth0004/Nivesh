const combo = [{ mode: 'lumpsum', amount: 50, price: 100, units: 0, type: 'stock' }];
const states = combo.map(a => ({ ...a, price: +a.price, units: 0 }));
let invested = 0;
let val = 0;
let day = 0;
for (const s of states) {
    if (day === 0 && s.mode === 'lumpsum') {
        s.units += s.amount;
        invested += s.amount * s.price;
    }
    val += s.units * s.price;
}
console.log('val', val, 'invested', invested);
