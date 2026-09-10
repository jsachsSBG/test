"""Build the plain-language New Business story page (HTML + inline SVG) from out/metrics.json."""
import json, math, os, sys, html as H

S = os.environ.get('S', '/tmp/claude-0/-home-user-test/4450fde6-d7f1-5400-906d-a37991314de6/scratchpad')
R = json.load(open(f'{S}/out/metrics.json'))
Y = ['2023', '2024', '2025', '2026']
YL = {'2023': '2023', '2024': '2024', '2025': '2025', '2026': '2026 (Jan–Aug)'}
YS = {'2023': '2023', '2024': '2024', '2025': '2025', '2026': '2026*'}
YC = {'2023': 'var(--y23)', '2024': 'var(--y24)', '2025': 'var(--y25)', '2026': 'var(--y26)'}
SC = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)']

# ---------- formatting ----------
def K(v, d=0):
    return f"{v:,.{d}f}"
def M(v):
    if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
    if abs(v) >= 1e3: return f"${v/1e3:.1f}K" if v < 1e5 else f"${v/1e3:.0f}K"
    return f"${v:,.0f}"
def P(v, d=0):
    return f"{v*100:.{d}f}%"
def yr(d, k=None):
    return [d[y] if k is None else d[y][k] for y in Y]
def ratio(a, b):
    return a / b if b else 0
def nice_step(span):
    if span <= 0: return 1
    raw = span / 4
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag: return m * mag
    return 10 * mag

# ---------- SVG helpers ----------
def _yaxis(ymax, ymin=0):
    step = nice_step(ymax - ymin)
    top = math.ceil(ymax / step) * step
    if top == ymax: top += 0  # keep
    ticks = []
    v = ymin
    while v <= top + 1e-9:
        ticks.append(v); v += step
    return top, ticks

def line_chart(xlabels, series, yfmt=lambda v: f"{v:,.0f}", h=280, w=880, ymin=0, ymax=None, xticks=None, colors=None, end_labels=True, note=None):
    """series: list of (name, values[None allowed]). Returns HTML with svg + legend."""
    colors = colors or SC
    allv = [v for _, vals in series for v in vals if v is not None]
    if ymax is None: ymax = max(allv) if allv else 1
    top, ticks = _yaxis(ymax, ymin)
    pl, pr, pt, pb = 64, (120 if end_labels else 20), 16, 34
    iw, ih = w - pl - pr, h - pt - pb
    n = len(xlabels)
    def X(i): return pl + (i / max(n - 1, 1)) * iw
    def Yv(v): return pt + ih - (v - ymin) / (top - ymin) * ih
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for t in ticks:
        out.append(f'<line x1="{pl}" y1="{Yv(t):.1f}" x2="{pl+iw}" y2="{Yv(t):.1f}" class="grid"/>')
        out.append(f'<text x="{pl-8}" y="{Yv(t)+4:.1f}" text-anchor="end" class="tick">{yfmt(t)}</text>')
    xt = xticks if xticks is not None else list(range(n))
    for i in xt:
        out.append(f'<text x="{X(i):.1f}" y="{h-10}" text-anchor="middle" class="tick">{H.escape(str(xlabels[i]))}</text>')
    used_y = []
    for si, (name, vals) in enumerate(series):
        c = colors[si % len(colors)]
        pts = [(X(i), Yv(v)) for i, v in enumerate(vals) if v is not None]
        if not pts: continue
        d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        if len(pts) <= 6:
            for x, y in pts: out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{c}"/>')
        if end_labels:
            x, y = pts[-1]
            # avoid overlaps
            while any(abs(y - u) < 14 for u in used_y): y += 14
            used_y.append(y)
            out.append(f'<text x="{x+8:.1f}" y="{y+4:.1f}" class="endlbl" fill="{c}">{H.escape(name)}</text>')
    out.append('</svg>')
    leg = ''
    if len(series) >= 2:
        leg = '<div class="legend">' + ''.join(f'<span><i style="background:{colors[i%len(colors)]}"></i>{H.escape(nm)}</span>' for i, (nm, _) in enumerate(series)) + '</div>'
    return f'<figure><div class="fig">{"".join(out)}</div>{leg}{f"<figcaption>{note}</figcaption>" if note else ""}</figure>'

def bar_chart(cats, series, yfmt=lambda v: f"{v:,.0f}", h=280, w=880, colors=None, value_labels=True, vfmt=None, note=None):
    """grouped vertical bars. series: list of (name, values)."""
    colors = colors or SC
    vfmt = vfmt or yfmt
    allv = [v for _, vals in series for v in vals if v is not None]
    top, ticks = _yaxis(max(allv) * 1.12 if allv else 1)
    pl, pr, pt, pb = 64, 16, 16, 34
    iw, ih = w - pl - pr, h - pt - pb
    n, m = len(cats), len(series)
    gw = iw / n
    bw = gw * 0.72 / m
    def Yv(v): return pt + ih - v / top * ih
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for t in ticks:
        out.append(f'<line x1="{pl}" y1="{Yv(t):.1f}" x2="{pl+iw}" y2="{Yv(t):.1f}" class="grid"/>')
        out.append(f'<text x="{pl-8}" y="{Yv(t)+4:.1f}" text-anchor="end" class="tick">{yfmt(t)}</text>')
    for ci, c in enumerate(cats):
        x0 = pl + ci * gw + gw * 0.14
        out.append(f'<text x="{pl + ci*gw + gw/2:.1f}" y="{h-10}" text-anchor="middle" class="tick">{H.escape(str(c))}</text>')
        for si, (name, vals) in enumerate(series):
            v = vals[ci]
            if v is None: continue
            x = x0 + si * bw
            out.append(f'<rect x="{x:.1f}" y="{Yv(v):.1f}" width="{bw-2:.1f}" height="{ih - (Yv(v)-pt):.1f}" fill="{colors[si%len(colors)]}" rx="2"/>')
            if value_labels and m <= 4:
                out.append(f'<text x="{x + (bw-2)/2:.1f}" y="{Yv(v)-4:.1f}" text-anchor="middle" class="vlbl">{H.escape(vfmt(v))}</text>')
    out.append('</svg>')
    leg = ''
    if m >= 2:
        leg = '<div class="legend">' + ''.join(f'<span><i style="background:{colors[i%len(colors)]}"></i>{H.escape(nm)}</span>' for i, (nm, _) in enumerate(series)) + '</div>'
    return f'<figure><div class="fig">{"".join(out)}</div>{leg}{f"<figcaption>{note}</figcaption>" if note else ""}</figure>'

def year_bars(cats, valfn, yfmt, vfmt=None, h=260, note=None):
    """cats: list of labels; valfn(cat, y) -> value. one series per year."""
    series = [(YS[y], [valfn(c, y) for c in cats]) for y in Y]
    return bar_chart(cats, series, yfmt=yfmt, vfmt=vfmt, h=h, colors=[YC[y] for y in Y], note=note)

def hbar(items, vfmt=lambda v: f"{v:,.0f}", color='var(--s1)', w=880, maxv=None, note=None):
    """items: list of (label, value)."""
    rh = 28
    h = rh * len(items) + 8
    lw = 250
    maxv = maxv or max(v for _, v in items) or 1
    iw = w - lw - 90
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for i, (lab, v) in enumerate(items):
        y = 4 + i * rh
        bw = max(0, v / maxv * iw)
        out.append(f'<text x="{lw-10}" y="{y+18}" text-anchor="end" class="hlbl">{H.escape(str(lab))}</text>')
        out.append(f'<rect x="{lw}" y="{y+5}" width="{bw:.1f}" height="{rh-10}" fill="{color}" rx="3"/>')
        out.append(f'<text x="{lw+bw+8:.1f}" y="{y+18}" class="vlbl">{H.escape(vfmt(v))}</text>')
    out.append('</svg>')
    return f'<figure><div class="fig">{"".join(out)}</div>{f"<figcaption>{note}</figcaption>" if note else ""}</figure>'

def table(headers, rows, cls='', align_first_left=True, foot=None):
    th = ''.join(f'<th>{h}</th>' for h in headers)
    trs = []
    for r in rows:
        tds = ''.join(f'<td>{c}</td>' for c in r)
        trs.append(f'<tr>{tds}</tr>')
    ft = f'<p class="tfoot">{foot}</p>' if foot else ''
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>{ft}'

def trend(vals, higher_is_good=True, thresh=0.03):
    """word for direction 2023 -> 2026"""
    a, b = vals[0], vals[-1]
    if a == 0: return 'new'
    ch = (b - a) / abs(a)
    if abs(ch) < thresh: return 'flat'
    up = ch > 0
    good = (up == higher_is_good)
    word = 'up' if up else 'down'
    return f'{word} {abs(ch)*100:.0f}% ({"good" if good else "worse"})'

def chip(txt, kind):
    return f'<span class="chip {kind}">{txt}</span>'

# ---------- data prep ----------
L = R['leads_created_mavg']; K3 = R['leads_300k_created_mavg']; A = R['assigned_mavg']; A3 = R['assigned_300k_mavg']
O = R['opps_created_mavg']; AP = R['approved_mavg']; F = R['funded_mavg']; FA = R['funded_amt_mavg']; RV = R['sbg_rev_mavg']
HC = R['headcount_mavg']['reps_ae']; VSS = R['headcount_mavg']['reps_vss']; HCALL = R['headcount_mavg']['reps_all']
PR = R['per_rep_mavg']
GI = R['growth_index']
months = [r['ym'] for r in R['dl_month_table']]
mlab = []
for ym in months:
    yy, mm = divmod(int(ym), 100)
    mlab.append(f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][mm-1]} {str(yy)[2:]}")
jan_idx = [i for i, ym in enumerate(months) if int(ym) % 100 == 1]
dl = {r['ym']: r for r in R['dl_month_table']}
om = {int(r['ym']): r for r in R['opp_month_table']}
lm = {r['ym']: r for r in R['lead_month_table']}
hm = {r['ym']: r for r in R['headcount_table']}
pm = {r['ym']: r for r in R['per_rep_table']}
sm = {r['ym']: r for r in R['subs_month_table']}
cm = {int(r['cym']): r for r in R['cycle_month_table']}

def per100(y):
    l = L[y]
    return dict(created=100, assigned=R['assigned_pct_of_created'][y]*100, opps=O[y]/l*100, approved=AP[y]/l*100, funded=F[y]/l*100)

# manager tables
MA = {(r['manager'], r['yr']): r for r in R['manager_attrib_rank']}
MT = {(r['manager'], r['yr']): r for r in R['manager_tenure']}
def mgr_rows(y):
    rows = [r for r in R['manager_attrib_rank'] if r['yr'] == y]
    rows.sort(key=lambda r: r['composite'])
    return rows

# segments
def seg_rows(key, label, order=None, minopps=150, metric='close_on_subs', top=None):
    rows = R[key]
    labels = order or sorted({r[label] for r in rows}, key=str)
    tot = {y: sum(r['opps'] for r in rows if str(r['cyr']) == y) for y in Y}
    out = []
    for l in labels:
        d = {str(r['cyr']): r for r in rows if r[label] == l}
        if not d or max(d[y]['opps'] for y in d) < minopps: continue
        out.append((l, d, tot))
    if top:
        out.sort(key=lambda t: -t[1].get('2026', {'opps': 0})['opps'])
        out = out[:top]
    return out

def seg_table(key, label, order=None, minopps=150, metric='close_on_subs', top=None, name_map=None, share_key='opps', metric_name='Close rate on submissions'):
    rows = seg_rows(key, label, order, minopps, metric, top)
    hdr = ['Group'] + [f'{YS[y]} close' for y in Y] + ['Share of 2026 opps', '2026 avg deal']
    body = []
    for l, d, tot in rows:
        nm = (name_map or {}).get(l, l) or '(blank)'
        cells = [H.escape(str(nm))]
        for y in Y:
            cells.append(P(d[y][metric], 1) if y in d and d[y][share_key] > 0 else '–')
        if '2026' in d:
            cells.append(P(d['2026'][share_key] / tot['2026'], 0) if tot['2026'] else '–')
            ad = d['2026']['avg_deal']
            cells.append(M(ad) if ad == ad and ad else '–')
        else:
            cells += ['–', '–']
        body.append(cells)
    return table(hdr, body)

# ---------- page ----------
css = """
:root{--bg:#f7f6f2;--card:#ffffff;--text:#1d1d1b;--muted:#63625d;--line:#e3e1da;--grid:#e6e4de;--accent:#2a78d6;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#4a3aa7;--s8:#e34948;
--y23:#9aa3ad;--y24:#1baf7a;--y25:#2a78d6;--y26:#eb6834;--good:#0f7a3d;--goodbg:#e4f5ea;--bad:#b3261e;--badbg:#fbe7e5;--warn:#8a5a00;--warnbg:#fff1d6;--soft:#eef3fb;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#151514;--card:#1f1f1d;--text:#ececea;--muted:#a9a8a2;--line:#33332f;--grid:#33332f;--accent:#6aa5ee;
--s1:#6aa5ee;--s2:#f28a5c;--s3:#3ccf98;--s4:#f5be3c;--s5:#f09bbb;--s6:#4fc04f;--s7:#8f82d8;--s8:#f07070;
--y23:#7d8791;--y24:#3ccf98;--y25:#6aa5ee;--y26:#f28a5c;--good:#6fd39a;--goodbg:#173a26;--bad:#f28b85;--badbg:#42211f;--warn:#f0c264;--warnbg:#3d2f10;--soft:#232a36;}}
:root[data-theme="dark"]{--bg:#151514;--card:#1f1f1d;--text:#ececea;--muted:#a9a8a2;--line:#33332f;--grid:#33332f;--accent:#6aa5ee;
--s1:#6aa5ee;--s2:#f28a5c;--s3:#3ccf98;--s4:#f5be3c;--s5:#f09bbb;--s6:#4fc04f;--s7:#8f82d8;--s8:#f07070;
--y23:#7d8791;--y24:#3ccf98;--y25:#6aa5ee;--y26:#f28a5c;--good:#6fd39a;--goodbg:#173a26;--bad:#f28b85;--badbg:#42211f;--warn:#f0c264;--warnbg:#3d2f10;--soft:#232a36;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:17px;line-height:1.55;padding-inline:20px;padding-block:24px 60px;}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:2.1rem;line-height:1.15;margin:0 0 6px}
h2{font-size:1.5rem;margin:0 0 4px;line-height:1.2}
h3{font-size:1.12rem;margin:22px 0 6px}
.sub{color:var(--muted);margin:0 0 22px;font-size:1rem}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 22px 18px;margin:18px 0}
section>.kicker{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.plain{background:var(--soft);border-radius:10px;padding:12px 16px;margin:10px 0 14px;font-size:1.02rem}
.plain b{font-weight:700}
.big{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
.big .n{background:var(--soft);border-radius:10px;padding:12px 14px}
.big .n .v{font-size:1.6rem;font-weight:700;line-height:1.1}
.big .n .l{font-size:.86rem;color:var(--muted);margin-top:4px}
.big .n .d{font-size:.86rem;margin-top:4px}
figure{margin:12px 0 6px}
figcaption{font-size:.86rem;color:var(--muted);margin-top:4px}
svg.chart{width:100%;height:auto;display:block;font-family:inherit}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .tick{font-size:12px;fill:var(--muted)}
svg .vlbl{font-size:12px;fill:var(--text)}
svg .hlbl{font-size:13px;fill:var(--text)}
svg .endlbl{font-size:12.5px;font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.86rem;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.tw{overflow-x:auto;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:.93rem}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
th{color:var(--muted);font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.04em}
.tfoot{color:var(--muted);font-size:.84rem;margin:4px 0 10px}
td:first-child,th:first-child{min-width:190px}
table.mgr td:first-child,table.mgr th:first-child{white-space:nowrap;min-width:0}
.fig{overflow-x:auto}
.fig svg.chart{min-width:560px}
.two .fig svg.chart{min-width:0}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.8rem;font-weight:600;white-space:nowrap}
.chip.good{background:var(--goodbg);color:var(--good)}.chip.bad{background:var(--badbg);color:var(--bad)}.chip.warn{background:var(--warnbg);color:var(--warn)}.chip.flat{background:var(--soft);color:var(--muted)}
ul{padding-left:22px}li{margin:6px 0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.funnels{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.funnel{background:var(--soft);border-radius:10px;padding:12px}
.funnel h4{margin:0 0 8px;font-size:1rem}
.frow{display:grid;grid-template-columns:82px 1fr 46px;align-items:center;gap:8px;font-size:.84rem;margin:5px 0}
.frow .bar{height:14px;border-radius:4px;background:var(--y25)}
.frow .bar.c{background:var(--muted);opacity:.55}
.frow .v{text-align:right;font-weight:600}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.toc a{font-size:.86rem;background:var(--soft);padding:4px 10px;border-radius:999px;text-decoration:none;color:var(--text)}
.note{font-size:.9rem;color:var(--muted)}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.grade .g{border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.grade .g b{display:block;font-size:1.02rem;margin-bottom:4px}
.sw{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.sw .box{border-radius:10px;padding:14px 16px}
.sw .box h3{margin:0 0 8px}
.sw .box ul{margin:0;padding-left:18px}
.sw .box li{font-size:.95rem}
.sw .good{background:var(--goodbg)}.sw .bad{background:var(--badbg)}.sw .warn{background:var(--warnbg)}.sw .soft{background:var(--soft)}
@media (max-width:520px){body{font-size:16px}h1{font-size:1.7rem}section{padding:16px 14px}}
"""

parts = []
def add(s): parts.append(s)

# ===== Header =====
add(f"""<title>SBG New Business Story</title>
<style>{css}</style>
<div class="wrap">
<h1>How SBG&rsquo;s New Business Changed, 2023 to 2026</h1>
<p class="sub">A plain-words story of NEW business only (renewals are left out). Every number is a <b>monthly average</b> for the calendar year, so years can be compared even though 2026 only has January through August so far. Built from Salesforce leads, Distribution Engine logs, opportunities, and lender submissions on September 10, 2026. Wherever you see <b>2026*</b>, it means January&ndash;August 2026.</p>
<div class="toc">
<a href="#tldr">The short version</a><a href="#big">Big picture</a><a href="#funnel">The funnel</a><a href="#reps">Per salesperson</a><a href="#people">People vs. leads</a><a href="#managers">Managers</a><a href="#sources">Lead sources</a><a href="#routing">How leads get handed out</a><a href="#segments">What closes</a><a href="#speed">Speed</a><a href="#winback">Win-backs</a><a href="#season">Seasons</a><a href="#lenders">Lenders</a><a href="#why">Why deals die</a><a href="#verdict">Strengths &amp; problems</a><a href="#notes">Data notes</a>
</div>
""")

# ===== glossary + TLDR =====
g26 = GI['2026']
add(f"""
<section id="tldr"><div class="kicker">The short version</div>
<h2>Five things to know</h2>
<div class="plain">
<b>The words we use.</b> A <b>lead</b> is a business that raised its hand and asked about money. <b>Assigned</b> means the Distribution Engine handed that lead to a salesperson. An <b>opportunity (opp)</b> means the salesperson got the paperwork and sent the deal to lenders. <b>Approved</b> means at least one lender said yes. <b>Funded</b> means the money actually went out the door. <b>SBG revenue</b> is what SBG earns on a funded deal.
</div>
<ol>
<li><b>The machine got about 3&frac12; times bigger.</b> Compared with 2023, SBG now has {g26['reps_ae']/100:.1f}x the salespeople working new leads, hands out {g26['assigned']/100:.1f}x the leads, funds {g26['funded']/100:.1f}x the deals, and sends out {g26['funded_amt']/100:.1f}x the dollars every month.</li>
<li><b>Each salesperson does about the same as in 2023.</b> A rep funded {PR['funded_per_rep']['2023']:.1f} deals a month in 2023 and {PR['funded_per_rep']['2026']:.1f} in 2026, worth about {M(PR['rev_per_rep']['2023'])} then and {M(PR['rev_per_rep']['2026'])} now in SBG revenue. Growth came from adding people and leads, not from each person getting better.</li>
<li><b>The funnel leaks more at the top and the bottom.</b> A smaller share of new leads gets assigned ({P(R['assigned_pct_of_created']['2023'])} &rarr; {P(R['assigned_pct_of_created']['2026'])}). Lenders approve more deals ({P(R['approval_rate']['2023'])} &rarr; {P(R['approval_rate']['2026'])}), but fewer approvals turn into money ({P(R['close_on_approvals']['2023'])} &rarr; {P(R['close_on_approvals']['2026'])}). The loss moved to <i>after</i> the lender says yes.</li>
<li><b>Deals got bigger, SBG&rsquo;s slice got thinner.</b> The average funded deal grew from {M(R['avg_deal_size']['2023'])} to {M(R['avg_deal_size']['2026'])}, mostly thanks to Sofi referrals and bigger-business lead tiers. But SBG revenue per funded dollar slipped from {P(R['rev_pct_of_funded']['2023'],1)} to {P(R['rev_pct_of_funded']['2026'],1)}.</li>
<li><b>The biggest levers are clear.</b> (1) Fix the after-approval leak: closed-lost now eats {P(R['closed_lost_rate_of_approved']['2026'])} of approvals and &ldquo;lost contact with merchant&rdquo; has grown 4x. (2) Rebalance lead buying: businessloans.com conversion fell from 26% to 14% while Sofi, Bluevine and On Deck referrals convert 2&ndash;3x better. (3) Get new-hire teams productive faster; the managers running mostly new reps produce 25&ndash;45% less per rep.</li>
</ol>
</section>
""")

# ===== Big picture =====
gi_series = [(nm, [GI[y][k] for y in Y]) for nm, k in [('Salespeople (AEs)', 'reps_ae'), ('Leads assigned', 'assigned'), ('Opps created', 'opps'), ('Deals funded', 'funded'), ('Dollars funded', 'funded_amt'), ('SBG revenue', 'sbg_rev')]]
add(f"""
<section id="big"><div class="kicker">Big picture</div>
<h2>Everything roughly tripled. Salespeople grew fastest.</h2>
<div class="plain">If 2023 = 100, here is how big each piece of the business is now. The salesperson line is on top, which tells you headcount grew a bit faster than the results it produced.</div>
{line_chart([YS[y] for y in Y], gi_series, yfmt=lambda v: f"{v:.0f}", h=300, note='Index, 2023 monthly average = 100. 2026 is January–August monthly average.')}
<h3>The monthly averages behind that chart</h3>
{table(['Per month'] + [YL[y] for y in Y] + ['2023 to 2026'], [
 ['Leads created (all)'] + [K(L[y]) for y in Y] + [trend(yr(L))],
 ['Leads created with $300K+ revenue'] + [K(K3[y]) for y in Y] + [trend(yr(K3))],
 ['Unique leads assigned to new-biz reps'] + [K(A[y]) for y in Y] + [trend(yr(A))],
 ['&hellip;of which $300K+ revenue'] + [K(A3[y]) for y in Y] + [trend(yr(A3))],
 ['Opportunities created'] + [K(O[y]) for y in Y] + [trend(yr(O))],
 ['Opportunities approved'] + [K(AP[y]) for y in Y] + [trend(yr(AP))],
 ['Deals funded'] + [K(F[y]) for y in Y] + [trend(yr(F))],
 ['Dollars funded'] + [M(FA[y]) for y in Y] + [trend(yr(FA))],
 ['SBG revenue'] + [M(RV[y]) for y in Y] + [trend(yr(RV))],
 ['Average funded deal'] + [M(R['avg_deal_size'][y]) for y in Y] + [trend(yr(R['avg_deal_size']))],
 ['Average SBG revenue per deal'] + [M(R['avg_sbg_rev_per_deal'][y]) for y in Y] + [trend(yr(R['avg_sbg_rev_per_deal']))],
 ['SBG revenue as % of dollars funded'] + [P(R['rev_pct_of_funded'][y], 2) for y in Y] + [trend(yr(R['rev_pct_of_funded']))],
 ['Salespeople working new leads (AEs)'] + [K(HC[y], 1) for y in Y] + [trend(yr(HC))],
 ['VSS agents (small-deal phone team)'] + [K(VSS[y], 1) for y in Y] + ['new in 2024'],
], foot='&ldquo;Assigned&rdquo; comes from Distribution Engine logs, counting each business once per month and leaving out leads routed to the Renewals team. &ldquo;AEs&rdquo; are users with the Sales Rep or Sales Rep - Manager profile who touched at least 10 unique leads in the month.')}
<div class="plain"><b>What it means.</b> SBG bought and generated far more leads (4x), but only about 3.3x more got handed to reps, and about 3.3x more deals funded. Dollars funded grew faster (3.8x) because deals are bigger. Revenue grew a little slower than dollars (3.4x) because SBG keeps a smaller slice of each dollar than it used to.</div>
</section>
""")

# ===== Funnel =====
fun_rows = []
for y in Y:
    f = per100(y)
    fun_rows.append(f"""<div class="funnel"><h4>{YL[y]}</h4>
<div class="frow"><span>Created</span><div class="bar c" style="width:100%"></div><span class="v">100</span></div>
<div class="frow"><span>Assigned</span><div class="bar" style="width:{f['assigned']:.0f}%"></div><span class="v">{f['assigned']:.0f}</span></div>
<div class="frow"><span>Opp made</span><div class="bar" style="width:{f['opps']:.1f}%"></div><span class="v">{f['opps']:.1f}</span></div>
<div class="frow"><span>Approved</span><div class="bar" style="width:{f['approved']:.1f}%"></div><span class="v">{f['approved']:.1f}</span></div>
<div class="frow"><span>Funded</span><div class="bar" style="width:{max(f['funded'],0.6):.1f}%"></div><span class="v">{f['funded']:.1f}</span></div>
</div>""")
rate_series = [('Approval rate', [R['approval_rate'][y]*100 for y in Y]),
               ('Close on approvals', [R['close_on_approvals'][y]*100 for y in Y]),
               ('Assigned to opp', [R['assigned_conv_rate'][y]*100 for y in Y]),
               ('Close on submissions', [R['close_on_submissions'][y]*100 for y in Y])]
add(f"""
<section id="funnel"><div class="kicker">The funnel</div>
<h2>Out of every 100 leads created, about 2 get funded</h2>
<div class="plain">Think of the funnel as a slide with gates. Here is how many of every 100 leads make it through each gate.</div>
<div class="funnels">{''.join(fun_rows)}</div>
<figcaption>Per 100 leads created in the same period (monthly averages). Assigned = unique businesses handed to new-business reps by the Distribution Engine.</figcaption>
<h3>The gate-by-gate rates</h3>
{table(['Rate'] + [YL[y] for y in Y] + ['Direction'], [
 ['Assigned % of leads created (Distribution logs, unique per month)'] + [P(R['assigned_pct_of_created'][y], 1) for y in Y] + [trend(yr(R['assigned_pct_of_created']))],
 ['Assigned % of leads created (lead report, ever assigned)'] + [P(R['lead_assigned_ever_share'][y], 1) for y in Y] + [trend(yr(R['lead_assigned_ever_share']))],
 ['Re-assignments per unique lead (logs &divide; unique)'] + [f"{R['reassign_ratio'][y]:.2f}x" for y in Y] + ['spike in 2023, small rise in 2026'],
 ['$300K+ share of assigned leads'] + [P(R['assigned_300k_share'][y]) for y in Y] + [trend(yr(R['assigned_300k_share']))],
 ['Qualified % of first-assigned leads'] + [P(R['qualified_pct_of_first_assigned'][y], 1) for y in Y] + [trend(yr(R['qualified_pct_of_first_assigned']))],
 ['Assigned &rarr; opportunity (Distribution logs)'] + [P(R['assigned_conv_rate'][y], 1) for y in Y] + [trend(yr(R['assigned_conv_rate']))],
 ['Assigned &rarr; opportunity, $300K+ leads only'] + [P(R['assigned_300k_conv_rate'][y], 1) for y in Y] + [trend(yr(R['assigned_300k_conv_rate']))],
 ['Opps created per assigned lead'] + [f"{R['opps_per_assigned'][y]:.3f}" for y in Y] + [trend(yr(R['opps_per_assigned']))],
 ['Approval rate (approved &divide; opps)'] + [P(R['approval_rate'][y], 1) for y in Y] + [trend(yr(R['approval_rate']))],
 ['Decline rate (declined &divide; opps)'] + [P(R['decline_rate'][y], 1) for y in Y] + [trend(yr(R['decline_rate']), higher_is_good=False)],
 ['Close on approvals (funded &divide; approved)'] + [P(R['close_on_approvals'][y], 1) for y in Y] + [trend(yr(R['close_on_approvals']))],
 ['Closed-lost share of approved deals'] + [P(R['closed_lost_rate_of_approved'][y], 1) for y in Y] + [trend(yr(R['closed_lost_rate_of_approved']), higher_is_good=False)],
 ['Close on submissions (funded &divide; opps created)'] + [P(R['close_on_submissions'][y], 1) for y in Y] + [trend(yr(R['close_on_submissions']))],
 ['Close on assigned leads (funded &divide; unique assigned)'] + [P(R['close_on_assigned'][y], 1) for y in Y] + [trend(yr(R['close_on_assigned']))],
 ['Close on all leads created (funded &divide; created)'] + [P(R['close_on_created'][y], 1) for y in Y] + [trend(yr(R['close_on_created']))],
], foot='Two ways to count &ldquo;assigned&rdquo;: the Distribution Engine logs (true hand-offs, one business counted once per month) and the lead report (leads that were ever assigned). The log number is the one to trust; the gap between them grew because more leads now get re-routed as duplicates.')}
{line_chart([YS[y] for y in Y], rate_series, yfmt=lambda v: f"{v:.0f}%", h=300, note='Funnel rates by year (monthly-average basis).')}
<div class="plain"><b>What it means.</b> Lenders say yes more often than they used to (a real win, driven by the Sofi and bigger-business mix). But the share of approved deals that actually fund has slipped every single year, and the share of approvals ending as &ldquo;closed lost&rdquo; climbed from {P(R['closed_lost_rate_of_approved']['2023'])} to {P(R['closed_lost_rate_of_approved']['2026'])}. Overall, close on submissions is basically flat at 15&ndash;16%, so the whole funnel from lead to money is the same as 2023, just much bigger.</div>
<h3>Month by month</h3>
{line_chart(mlab, [('Assigned % of leads created', [R['assigned_pct_of_created_month'].get(str(m), None) and R['assigned_pct_of_created_month'][str(m)]*100 for m in months])], yfmt=lambda v: f"{v:.0f}%", h=220, xticks=jan_idx, end_labels=False, note='Share of leads created each month that were assigned by the Distribution Engine. January 2024 is the month lead buying jumped and assignment could not keep up.')}
</section>
""")

# ===== Per rep =====
pr_series_leads = [('Leads assigned per AE per month', [pm[m]['leads_per_rep'] for m in months])]
pr_series_opps = [('Opps per AE per month', [pm[m]['opps_per_rep'] for m in months])]
pr_series_f = [('Funded deals per AE per month', [pm[m]['funded_per_rep'] for m in months])]
pr_series_r = [('SBG revenue per AE per month', [pm[m]['rev_per_rep'] for m in months])]
add(f"""
<section id="reps"><div class="kicker">Per salesperson</div>
<h2>One rep, one month: about 250 leads, 57 opps, 9 funded deals</h2>
<div class="plain">This is the most important table in the report. If the business got better at selling, these numbers would go up. They did not. They are flat.</div>
{table(['Per AE per month'] + [YL[y] for y in Y] + ['Direction'], [
 ['Leads assigned'] + [K(PR['leads_per_rep'][y]) for y in Y] + [trend(yr(PR['leads_per_rep']))],
 ['Opportunities created'] + [K(PR['opps_per_rep'][y], 1) for y in Y] + [trend(yr(PR['opps_per_rep']))],
 ['Deals funded'] + [K(PR['funded_per_rep'][y], 1) for y in Y] + [trend(yr(PR['funded_per_rep']))],
 ['Dollars funded'] + [M(PR['funded_amt_per_rep'][y]) for y in Y] + [trend(yr(PR['funded_amt_per_rep']))],
 ['SBG revenue'] + [M(PR['rev_per_rep'][y]) for y in Y] + [trend(yr(PR['rev_per_rep']))],
 ['Average deal size (all new business)'] + [M(R['avg_deal_size'][y]) for y in Y] + [trend(yr(R['avg_deal_size']))],
 ['Average SBG revenue per deal'] + [M(R['avg_sbg_rev_per_deal'][y]) for y in Y] + [trend(yr(R['avg_sbg_rev_per_deal']))],
 ['Number of AEs (monthly average)'] + [K(HC[y], 1) for y in Y] + [trend(yr(HC))],
], foot='AE = Sales Rep or Sales Rep - Manager profile with at least 10 unique leads that month. VSS agents are excluded here (they work tiny deals; see the Managers section).')}
<div class="two">
{line_chart(mlab, pr_series_leads, yfmt=lambda v: f"{v:,.0f}", h=230, w=440, xticks=jan_idx, end_labels=False, note='Leads assigned per AE each month.')}
{line_chart(mlab, pr_series_f, yfmt=lambda v: f"{v:.0f}", h=230, w=440, xticks=jan_idx, end_labels=False, note='Deals funded per AE each month.')}
{line_chart(mlab, pr_series_opps, yfmt=lambda v: f"{v:.0f}", h=230, w=440, xticks=jan_idx, end_labels=False, note='Opportunities created per AE each month.')}
{line_chart(mlab, pr_series_r, yfmt=lambda v: f"${v/1000:.0f}K", h=230, w=440, xticks=jan_idx, end_labels=False, note='SBG revenue per AE each month.')}
</div>
<h3>The spread between reps</h3>
{table(['', *[YL[y] for y in Y]], [
 ['AEs who funded at least one deal'] + [K(R['rep_spread'][y]['aes_with_funding']) for y in Y],
 ['Share of fundings from the top 20% of AEs'] + [P(R['rep_spread'][y]['top20pct_share']) for y in Y],
 ['Share of fundings from the bottom 50% of AEs'] + [P(R['rep_spread'][y]['bottom50pct_share']) for y in Y],
 ['Typical full-year rep: funded deals per month (median)'] + [K(R['rep_spread'][y]['median_funded_per_month_fullyear_reps'], 1) for y in Y],
 ['Share of AE opps from reps in their first 6 months'] + [P(R['new_rep_opp_share'][y]) for y in Y],
])}
<div class="plain"><b>What it means.</b> A typical experienced rep funds 10&ndash;11 deals a month, every year. The team is now less top-heavy (the top 20% carried 49% of fundings in 2024, 35% now), which is healthy. But 2026&rsquo;s median slipped to {K(R['rep_spread']['2026']['median_funded_per_month_fullyear_reps'],1)}, and leads per rep in mid-2026 dropped under 200 for the first time, a sign that headcount is now growing faster than leads.</div>
</section>
""")

# ===== People vs leads =====
hc_series = [('AEs working leads', [hm[m]['reps_ae'] for m in months]), ('VSS agents', [hm[m]['reps_vss'] for m in months])]
lead_series = [('Unique leads assigned (hundreds)', [dl[m]['uleads']/100 for m in months]), ('Leads created (hundreds)', [lm[m]['created']/100 for m in months])]
fund_series = [('Deals funded', [om[m]['funded'] for m in months]), ('Opps created (tens)', [om[m]['opps']/10 for m in months])]
add(f"""
<section id="people"><div class="kicker">People vs. leads vs. deals</div>
<h2>Headcount kept climbing after lead growth slowed</h2>
<div class="plain">Leads roughly tripled by early 2025 and then flattened. Salespeople kept being added through 2026. Funded deals followed leads, not people.</div>
{line_chart(mlab, hc_series, yfmt=lambda v: f"{v:.0f}", h=220, xticks=jan_idx, end_labels=False, note='Salespeople active on new leads each month.')}
{line_chart(mlab, lead_series, yfmt=lambda v: f"{v:.0f}", h=220, xticks=jan_idx, end_labels=False, note='Leads per month, in hundreds (e.g. 250 = 25,000). Assigned counts each business once per month, renewals excluded.')}
{line_chart(mlab, fund_series, yfmt=lambda v: f"{v:.0f}", h=220, xticks=jan_idx, end_labels=False, note='Deals funded per month, and opportunities created per month in tens (e.g. 500 = 5,000).')}
{table(['Growth vs. 2023 (monthly avg)', *[YS[y] for y in Y]], [
 ['Salespeople (AEs)'] + [f"{GI[y]['reps_ae']/100:.2f}x" for y in Y],
 ['Unique leads assigned'] + [f"{GI[y]['assigned']/100:.2f}x" for y in Y],
 ['Opportunities'] + [f"{GI[y]['opps']/100:.2f}x" for y in Y],
 ['Deals funded'] + [f"{GI[y]['funded']/100:.2f}x" for y in Y],
 ['Dollars funded'] + [f"{GI[y]['funded_amt']/100:.2f}x" for y in Y],
 ['SBG revenue'] + [f"{GI[y]['sbg_rev']/100:.2f}x" for y in Y],
])}
<div class="plain"><b>What it means.</b> In 2024 and 2025, leads grew faster than people, so each rep stayed busy. In 2026 the order flipped: AEs are up {P(GI['2026']['reps_ae']/GI['2025']['reps_ae']-1)} on 2025 but assigned leads are up only {P(GI['2026']['assigned']/GI['2025']['assigned']-1)}. Unless lead flow grows again, adding reps will mostly split the same pie into smaller slices.</div>
</section>
""")

# ===== Managers =====
def mgr_table(y, label):
    rows = mgr_rows(y)
    body = []
    for i, r in enumerate(rows):
        t = MT.get((r['manager'], y), {})
        newshare = t.get('share_opps_new_reps', None)
        body.append([f"{i+1}. {H.escape(r['manager'])}", K(r['avg_reps'], 1), K(r['leads_per_rep_month']), P(r['conv_rate'], 1), P(r['approval_rate'], 1), P(r['close_on_approvals'], 1), P(r['close_on_subs'], 1), K(r['funded_per_rep_month'], 1), M(r['rev_per_rep_month']), M(r['avg_deal']), P(newshare) if newshare is not None else '–'])
    return f"<h3>{label}</h3>" + table(['Manager (ranked)', 'Reps', 'Leads / rep / mo', 'Lead &rarr; opp', 'Approval', 'Close on approvals', 'Close on subs', 'Funded / rep / mo', 'Revenue / rep / mo', 'Avg deal', 'Opps from reps &lt; 6 mo'], body, cls='mgr')

def mgr_chart(y, key, fmt, note):
    rows = sorted(mgr_rows(y), key=lambda r: -r[key])
    return hbar([(r['manager'], r[key]) for r in rows], vfmt=fmt, note=note)

th = {(r['team_hist'], r['cyr']): r for r in R['team_hist_year']}
def thr(t, y): return th.get((t, y))
add(f"""
<section id="managers"><div class="kicker">Managers and teams</div>
<h2>Who runs a strong team, and who is carrying the new hires</h2>
<div class="plain">A rep&rsquo;s manager is the person who managed them in that month (from the Distribution Engine&rsquo;s manager stamp, which starts November 2024). Deals are credited to the rep&rsquo;s manager at the time the opp was created. Ranking = average of rank on close-on-submissions, funded per rep per month, revenue per rep per month, and lead-to-opp conversion. The last column matters: a team full of brand-new reps will always look worse.</div>
{mgr_table(2026, '2026 (January–August)')}
{mgr_chart(2026, 'rev_per_rep_month', lambda v: M(v), 'SBG revenue per rep per month, 2026 (Jan–Aug).')}
{mgr_table(2025, '2025')}
{mgr_chart(2025, 'rev_per_rep_month', lambda v: M(v), 'SBG revenue per rep per month, 2025.')}
{mgr_table(2024, '2024 (November–December only, when the manager stamp begins)')}
<h3>The report card</h3>
<div class="grade">
<div class="g"><b>Kyle Lyons {chip('Strong, every year', 'good')}</b>Biggest team (13&ndash;18 reps), top-3 all three years, best deal size in 2026 ({M(MA[('Kyle Lyons',2026)]['avg_deal'])}) and revenue per rep of {M(MA[('Kyle Lyons',2026)]['rev_per_rep_month'])}/month with almost no new hires. The benchmark.</div>
<div class="g"><b>Andrew Wolff {chip('Strong, every year', 'good')}</b>Top-3 all three years. Best funded-per-rep in 2025 ({K(MA[('Andrew Wolff',2025)]['funded_per_rep_month'],1)}/month) and highest approval rate among big teams. Slight slip in 2026 close-on-approvals ({P(MA[('Andrew Wolff',2026)]['close_on_approvals'],1)}).</div>
<div class="g"><b>Cole Norman {chip('Strong', 'good')}</b>#1 in late 2024, dipped to mid-pack in 2025 while absorbing new reps, back to top-3 in 2026 with the biggest deals ({M(MA[('Cole Norman',2026)]['avg_deal'])}) and {M(MA[('Cole Norman',2026)]['rev_per_rep_month'])} revenue per rep per month.</div>
<div class="g"><b>Jared Berkey {chip('Strong', 'good')}</b>#1 in 2025 (best close-on-approvals, {P(MA[('Jared Berkey',2025)]['close_on_approvals'],1)}) with a small experienced team; still top-5 in 2026 as the team grew from 5 to 9 reps.</div>
<div class="g"><b>Cameron Clearfield {chip('Solid, steady', 'good')}</b>Mid-to-upper pack every year with the most experienced roster (median rep tenure 22&ndash;31 months). Best 2026 close-on-approvals of the big teams ({P(MA[('Cameron Clearfield',2026)]['close_on_approvals'],1)}) but lowest revenue per rep among the top five, so the team funds well but smaller.</div>
<div class="g"><b>Brendan Newberry {chip('Below pack, new-hire team', 'warn')}</b>New manager mid-2025. {P(MT[('Brendan Newberry',2025)]['share_opps_new_reps'])} of 2025 opps and {P(MT[('Brendan Newberry',2026)]['share_opps_new_reps'])} of 2026 opps came from reps under 6 months. Lowest funded per rep ({K(MA[('Brendan Newberry',2026)]['funded_per_rep_month'],1)}/month) and lowest close-on-approvals in 2026 ({P(MA[('Brendan Newberry',2026)]['close_on_approvals'],1)}).</div>
<div class="g"><b>Brian Kim {chip('Below pack, every year', 'bad')}</b>Ranked last or next-to-last all three years. Runs the new-hire bench ({P(MT[('Brian Kim',2026)]['share_opps_new_reps'])} of 2026 opps from reps under 6 months), so lower output is partly the job. But the team also has the smallest deals ({M(MA[('Brian Kim',2026)]['avg_deal'])}) and lowest revenue per rep ({M(MA[('Brian Kim',2026)]['rev_per_rep_month'])}) in 2026 despite the best approval rate ({P(MA[('Brian Kim',2026)]['approval_rate'],1)}). Approvals are not being closed.</div>
<div class="g"><b>Raphael Kanner {chip('Below pack, new-hire team', 'bad')}</b>Also a new-hire team ({P(MT[('Raphael Kanner',2026)]['share_opps_new_reps'])} of 2026 opps from reps under 6 months). Lowest close-on-approvals in 2025 and 2026 ({P(MA[('Raphael Kanner',2026)]['close_on_approvals'],1)}), and the lowest funded per rep in 2026 ({K(MA[('Raphael Kanner',2026)]['funded_per_rep_month'],1)}/month).</div>
<div class="g"><b>Frank Tricamo, Alexander Herrera {chip('Mid-pack, since departed', 'flat')}</b>Mid-pack in 2024 and 2025 with small teams; their reps rolled into other teams during 2025.</div>
<div class="g"><b>Adam Block, Jake Rotman {chip('Pools, not a fair comparison', 'flat')}</b>Adam Block manages the VSS phone team and the new-hire onboarding pool (2025: 76K unique leads, 19% lead-to-opp). Jake Rotman&rsquo;s pool gets fewer leads per rep ({K(R['manager_dl_year'][[r['manager']+str(r['yr']) for r in R['manager_dl_year']].index('Jake Rotman2026')]['leads_per_rep_month'])}/month in 2026). Both are excluded from the ranking.</div>
</div>
<h3>Two managers ran everything in 2023</h3>
{table(['Team stamp on opp', 'Year', 'Reps (avg)', 'Opps', 'Funded', 'Close on subs', 'Funded / rep / mo', 'Revenue / rep / mo'], [
 [t, str(y), K(thr(t,y)['avg_reps'],1), K(thr(t,y)['opps']), K(thr(t,y)['funded']), P(thr(t,y)['close_on_subs'],1), K(thr(t,y)['funded_per_rep_month'],1), M(thr(t,y)['rev_per_rep_month'])]
 for t, y in [('Team Jake',2023),('Team Adam',2023),('Team VSS',2024),('Team VSS',2025),('Team VSS',2026),('Unknown',2023),('Unknown',2026)] if thr(t,y)
], foot='Team stamp = DE_First_Assigned_Team on the opportunity. In 2023 all new-business reps sat under Jake Rotman or Adam Block; the two teams performed identically (about 5.3 funded per rep-month, 15–16% close on subs). Team VSS is the small-deal phone team: 7–9% close, $16–19K average deal. &ldquo;Unknown&rdquo; = deals with no distribution stamp (direct, referral, ops), which close 29–38% on subs because they arrive pre-qualified.')}
<div class="plain"><b>What it means.</b> Managers with experienced rosters (Lyons, Wolff, Norman, Berkey, Clearfield) all land within a narrow band: 9&ndash;10 funded per rep per month and $40&ndash;53K revenue per rep per month in 2026. The gap to the new-hire managers (Kim, Kanner, Newberry: 7&ndash;8 funded, $29&ndash;36K) is 25&ndash;45%. The real question is not &ldquo;who is the best manager&rdquo; but &ldquo;why do new reps take so long to close approvals&rdquo;: reps in their first 3 months close {P([r for r in R['tenure_year'] if r['cyr']==2026 and r['tenband']=='0-3 mo'][0]['close_on_subs'],1)} of submissions vs {P([r for r in R['tenure_year'] if r['cyr']==2026 and r['tenband']=='25-48 mo'][0]['close_on_subs'],1)} for reps with 2&ndash;4 years.</div>
</section>
""")

# ===== Lead sources =====
src_order = ['Lending Tree', 'businessloans.com', 'Fundera', 'Sofi', 'Bluevine', 'Online Application', 'All other']
AS = {(r['src'], r['yr']): r for r in R['assigned_source_year']}
SE = {(r['lead_source'], r['yr']): r for r in R['source_economics_year']}
SS = {(r['src'], r['cyr']): r for r in R['seg_source']}
def asv(s, y, k, fmt):
    r = AS.get((s, int(y)))
    return fmt(r[k]) if r else '–'
src_share_rows = [[H.escape(s)] + [asv(s, y, 'share', lambda v: P(v)) for y in Y] + [asv(s, y, 'conv_rate', lambda v: P(v)) for y in Y] for s in src_order]
econ_rows = []
for s in ['Sofi', 'Bluevine', 'Online Application', 'Lending Tree', 'businessloans.com', 'Fundera']:
    row = [H.escape(s)]
    for y in Y:
        r = SE.get((s, int(y)))
        row.append(f"{r['funded_per_1000_assigned']:.0f}" if r else '–')
    for y in Y:
        r = SE.get((s, int(y)))
        row.append(f"${r['rev_per_assigned_lead']:.0f}" if r else '–')
    for y in ['2026']:
        r = SS.get((s, 2026))
        row.append(M(r['avg_deal']) if r else '–')
    econ_rows.append(row)
econ26 = sorted([(s, SE[(s, 2026)]['rev_per_assigned_lead']) for s in ['Sofi', 'Online Application', 'Bluevine', 'Lending Tree', 'businessloans.com', 'Fundera'] if (s, 2026) in SE], key=lambda t: -t[1])
CT = {(r['Lead_Source_Campaign_Type__c'], r['cyr']): r for r in R['seg_campaign_type']}
add(f"""
<section id="sources"><div class="kicker">Lead sources</div>
<h2>The big lead vendors are converting worse; referral partners convert 2&ndash;3x better</h2>
<div class="plain">Where assigned leads come from, and how often each source turns into an opportunity. Share = share of unique assigned leads that year.</div>
{table(['Source', *[f'{YS[y]} share' for y in Y], *[f'{YS[y]} lead&rarr;opp' for y in Y]], src_share_rows, foot='Sources with under 2% share are grouped in &ldquo;All other&rdquo;. Lending Tree share fell in 2026 because Fundera, Sofi and Bluevine volume was added, not because Lending Tree was cut.')}
<h3>What each source is really worth</h3>
<div class="plain">Two ways to judge a source: how many funded deals you get per 1,000 leads assigned, and how much SBG revenue you get per assigned lead.</div>
{table(['Source', *[f'{YS[y]} funded per 1,000' for y in Y], *[f'{YS[y]} revenue per lead' for y in Y], '2026 avg deal'], econ_rows)}
{hbar(econ26, vfmt=lambda v: f"${v:,.0f}", color='var(--y26)', note='SBG revenue per assigned lead, 2026 (Jan–Aug). Sofi leads are worth about 7x a businessloans.com lead.')}
<h3>Paid leads vs. revenue-share leads</h3>
{table(['Type', *[f'{YS[y]} share of opps' for y in Y], *[f'{YS[y]} close on subs' for y in Y], *[f'{YS[y]} avg deal' for y in Y]], [
 [t] + [P(CT[(t, int(y))]['opps'] / (CT[('CPL', int(y))]['opps'] + CT[('RS', int(y))]['opps'])) if (t, int(y)) in CT else '–' for y in Y] + [P(CT[(t, int(y))]['close_on_subs'],1) if (t, int(y)) in CT else '–' for y in Y] + [M(CT[(t, int(y))]['avg_deal']) if (t, int(y)) in CT else '–' for y in Y]
 for t in ['CPL', 'RS']], foot='CPL = cost-per-lead (paid up front). RS = revenue share (partner is paid when a deal funds). RS grew from 15% of opps to 49% and closes better with bigger deals.')}
<div class="plain"><b>What it means.</b> businessloans.com went from the best big source (26% lead-to-opp, $136 revenue per lead in 2023) to the worst (14%, $65). Fundera is similar ($109 to $47). Lending Tree fell and then held at about $70&ndash;$83. Meanwhile Sofi leads convert 44&ndash;47%, fund 100+ deals per 1,000 leads and bring $565&ndash;$659 per lead; Bluevine and On Deck referrals (25&ndash;26% close on submissions, $60K+ deals) are the next tier. Every marginal dollar of lead spend should be judged against these numbers.</div>
</section>
""")

# ===== Routing =====
DF = {(r['fam'], r['yr']): r for r in R['distributor_family_year']}
fam_order = ['Round-robin sales teams', 'VSS (virtual sales)', 'Sofi partner distributors', 'Bluevine partner distributor', 'ATC redistribution', 'Nurture', 'Online applications', 'Misc leads', 'Review queue', 'Deal-lost win-back', 'New-lead-source vetting', 'SEM', 'Other / tests']
fams = sorted({r['fam'] for r in R['distributor_family_year']}, key=lambda f: fam_order.index(f) if f in fam_order else 99)
fam_rows = []
for f in fams:
    if max(DF[(f, int(y))]['uleads'] for y in Y if (f, int(y)) in DF) < 500: continue
    fam_rows.append([H.escape(f)] + [P(DF[(f, int(y))]['share']) if (f, int(y)) in DF else '–' for y in Y] + [P(DF[(f, int(y))]['conv_rate']) if (f, int(y)) in DF else '–' for y in Y])
RR = {(r['team'], r['yr']): r for r in R['rr_team_year']}
SD = {(r['DE_Initial_Distributor__c'], r['cyr']): r for r in R['seg_distributor']}
tier_rows = []
for t in ['Team 1', 'Team 2', 'Team 3', 'Team 4', 'Team 5', 'Team 6']:
    n = t.split()[1]
    tier_rows.append([t] + [P(RR[(t, int(y))]['share']) if (t, int(y)) in RR and RR[(t, int(y))]['uleads'] > 100 else '–' for y in ['2024', '2025', '2026']] + [P(RR[(t, int(y))]['conv_rate']) if (t, int(y)) in RR and RR[(t, int(y))]['uleads'] > 100 else '–' for y in ['2024', '2025', '2026']] + [P(SD[(n, 2026)]['close_on_subs'],1) if (n, 2026) in SD else '–', M(SD[(n, 2026)]['avg_deal']) if (n, 2026) in SD else '–'])
add(f"""
<section id="routing"><div class="kicker">How leads get handed out</div>
<h2>From three round-robin teams to size-based tiers plus partner queues</h2>
<div class="plain">The Distribution Engine decides who gets each lead. Here is how that changed. Share = share of unique assigned leads; conversion = lead to opportunity.</div>
<ul>
<li><b>2023:</b> Three round-robin teams (A, B, C) took {P(DF[('Round-robin sales teams',2023)]['share'])} of leads. Another {P(DF[('ATC redistribution',2023)]['share'])} were &ldquo;attempting to contact&rdquo; leads recycled to a second rep (they converted only {P(DF[('ATC redistribution',2023)]['conv_rate'])}). Leads were re-assigned 1.27 times each on average.</li>
<li><b>2024:</b> Teams A/B/C became Teams 1&ndash;6, which are <b>lead tiers by business size</b>, not manager teams (the same 95 reps are members of Teams 2&ndash;7). A new VSS phone team took {P(DF[('VSS (virtual sales)',2024)]['share'])} of leads (small businesses) and the Sofi partner queue started.</li>
<li><b>2025:</b> Round-robin tiers took {P(DF[('Round-robin sales teams',2025)]['share'])} of leads, Sofi {P(DF[('Sofi partner distributors',2025)]['share'])}; VSS was wound down to almost nothing; ATC recycling stopped.</li>
<li><b>2026:</b> Round-robin {P(DF[('Round-robin sales teams',2026)]['share'])}, Sofi {P(DF[('Sofi partner distributors',2026)]['share'])}, Bluevine queue added, ATC redistribution brought back ({P(DF[('ATC redistribution',2026)]['share'])} of leads, converting {P(DF[('ATC redistribution',2026)]['conv_rate'])}), and a &ldquo;Redistribution&rdquo; flag now marks {P(R['redistribution_share_2026'])} of all log entries. Reassignments per lead ticked up to 1.08x.</li>
</ul>
{table(['Distributor family', *[f'{YS[y]} share' for y in Y], *[f'{YS[y]} lead&rarr;opp' for y in Y]], fam_rows)}
<h3>The size tiers (Distribution Teams 1&ndash;6)</h3>
{table(['Tier', '2024 share', '2025 share', '2026 share', '2024 lead&rarr;opp', '2025 lead&rarr;opp', '2026 lead&rarr;opp', '2026 close on subs', '2026 avg deal'], tier_rows, foot='Team 1 = smallest businesses (now mostly the new-hire and VSS pool); Team 6 = largest. Bigger tiers convert and close better and write much bigger deals.')}
<div class="plain"><b>What it means.</b> Routing has become smarter: the biggest businesses (Tiers 5 and 6) grew from 12% of leads in 2024 to 32% in 2026, and they convert 27&ndash;29% vs 18&ndash;22% for the small tiers. The weak spots are (1) the smallest tier still gets 9% of leads at 8.6% close on submissions and $14K deals, and (2) ATC recycling is back at a 6% conversion, which mostly adds reassignment noise. Note the Renewals distribution team also received about 18&ndash;19K existing-customer leads per year in 2025&ndash;26; those are excluded from every new-business number here.</div>
</section>
""")

# ===== Segments =====
fico_order = ['<580', '580 - 619', '620 - 649', '650 - 699', '700 - 749', '750 - 799', '800+']
rev_order = ['<200k', '200k - 400k', '400k - 500k', '500k - 700k', '700k - 1M', '1M - 2M', '2M - 4M', '4M - 6M', '6M+']
app_order = ['1-25K', '25-50K', '50-100K', '100-250K', '250-500K', '500K+']
AB = {(r['app_band'], r['cyr']): r for r in R['seg_approval_band']}
app_rows = []
for b in app_order:
    tot = {y: sum(r['approved'] for r in R['seg_approval_band'] if r['cyr'] == int(y)) for y in Y}
    app_rows.append([b] + [P(AB[(b, int(y))]['close_on_approvals'], 1) for y in Y] + [P(AB[(b, 2026)]['approved'] / tot['2026'])] + [M(AB[(b, 2026)]['avg_deal'])])
ind_top = seg_rows('seg_industry', 'Account_Industry__c', minopps=600, top=10)
PM = R['product_mix_funded_year']
def pmix(y, p):
    d = PM[f'{y}.0']; tot = sum(d.values()); return d.get(p, 0) / tot if tot else 0
add(f"""
<section id="segments"><div class="kicker">What kind of deals close</div>
<h2>Bigger, cleaner businesses close 2&ndash;4x more often</h2>
<div class="plain">&ldquo;Close rate on submissions&rdquo; = funded deals divided by opportunities created in that group. Share = that group&rsquo;s share of 2026 opportunities.</div>
<h3>By approval size</h3>
{table(['Largest approval', *[f'{YS[y]} close on approvals' for y in Y], 'Share of 2026 approvals', '2026 avg funded'], app_rows, foot='Close rate here = funded &divide; approved, by the largest approval on the opp. The under-$25K band is a third of approvals but closes worst; the $50–100K band has slipped the most (41% to 30%).')}
{year_bars(app_order, lambda b, y: AB[(b, int(y))]['close_on_approvals']*100, yfmt=lambda v: f"{v:.0f}%", vfmt=lambda v: f"{v:.0f}", h=250, note='Close rate on approvals by approval size band.')}
<h3>By credit score (FICO band on the opp)</h3>
{seg_table('seg_fico_band', 'A_FICO_Band__c', order=fico_order)}
<h3>By credit rating</h3>
{seg_table('seg_credit_rating', 'Credit_Rating__c', order=['Poor', 'Fair', 'Good', 'Excellent'])}
<h3>By annual revenue of the business</h3>
{seg_table('seg_rev_band', 'Annual_Revenue_Band__c', order=rev_order)}
<h3>By industry (top 10 by 2026 volume)</h3>
{seg_table('seg_industry', 'Account_Industry__c', minopps=600, top=10)}
<h3>By product funded</h3>
{table(['Product', *[f'{YS[y]} share of fundings' for y in Y], *[f'{YS[y]} close on subs' for y in Y]], [
 [p] + [P(pmix(y, p)) for y in Y] + [P([r for r in R['seg_product'] if r['Product__c'] == p and r['cyr'] == int(y)][0]['close_on_subs']) if [r for r in R['seg_product'] if r['Product__c'] == p and r['cyr'] == int(y)] else '–' for y in Y]
 for p in ['MCA', 'Line of Credit', 'Term Loan', 'Revolving MCA', 'SBA']], foot='Product is usually set only once a deal is approved, so close rates by product are high and mostly show which products fund once offered. Line-of-credit fundings fell from 63% to 48% close; term loans grew from 12% to 16% of fundings.')}
<div class="plain"><b>What it means.</b> Sub-580 credit is now {P([r for r in R['seg_fico_band'] if r['A_FICO_Band__c']=='<580' and r['cyr']==2026][0]['opps']/sum(r['opps'] for r in R['seg_fico_band'] if r['cyr']==2026))} of opportunities (up from 23%) and closes only {P([r for r in R['seg_fico_band'] if r['A_FICO_Band__c']=='<580' and r['cyr']==2026][0]['close_on_subs'],1)}. &ldquo;Poor&rdquo; credit rating is half of all opps at a 10% close. Businesses under $200K revenue close 5&ndash;6%. Healthcare (24%), manufacturing, and $1M+ businesses close 20&ndash;27% with $70&ndash;170K deals. Transportation is a seventh of opps at a 10% close. The fastest way to lift close rates is to send fewer low-credit, low-revenue leads to reps, or route them to a cheaper process.</div>
</section>
""")

# ===== Speed =====
CL, CF, CA, CFULL = R['cycle_lead_to_opp'], R['cycle_opp_to_fund'], R['cycle_opp_to_approve'], R['cycle_full']
add(f"""
<section id="speed"><div class="kicker">Speed</div>
<h2>Fast deals are still fast; slow deals got slower</h2>
{table(['Days', *[YL[y] for y in Y]], [
 ['Lead assigned &rarr; opportunity, typical (median)'] + [K(CL[y]['median'], 1) for y in Y],
 ['&hellip;average (mean)'] + [K(CL[y]['mean'], 1) for y in Y],
 ['&hellip;share converted the same day'] + [P(CL[y]['same_day_share']) for y in Y],
 ['Opportunity &rarr; approved, typical'] + [K(CA[y]['median'], 1) for y in Y],
 ['Opportunity &rarr; funded, typical (median)'] + [K(CF[y]['median'], 1) for y in Y],
 ['&hellip;average (mean)'] + [K(CF[y]['mean'], 1) for y in Y],
 ['&hellip;share funded within 7 days'] + [P(CF[y]['within_7d']) for y in Y],
 ['Lead assigned &rarr; funded, typical (median)'] + [K(CFULL[y]['median'], 1) for y in Y],
 ['&hellip;average (mean)'] + [K(CFULL[y]['mean'], 1) for y in Y],
])}
{line_chart(mlab, [('Median days: assigned to opp', [cm[m]['median_l2o'] for m in months]), ('Median days: opp to funded', [cm[m]['median_o2f'] for m in months])], yfmt=lambda v: f"{v:.1f}", h=230, xticks=jan_idx, end_labels=False, note='Typical (median) days by month the opp was created.')}
<div class="plain"><b>What it means.</b> Half of leads still become an opportunity within about a day, and half of funded deals still fund within 3 days of the opp. But the averages doubled (assigned-to-funded mean {K(CFULL['2023']['mean'])} days in 2023, {K(CFULL['2026']['mean'])} in 2026) because a long tail of leads now sits for weeks before a rep converts them, and a bigger share of funded deals take more than a week. Slow follow-up on the tail is where &ldquo;lost contact&rdquo; comes from.</div>
</section>
""")

# ===== Win-back =====
WB = {int(r['yr']): r for r in R['winback_year']}
DLS = R['deal_lost_src_opps_year']
add(f"""
<section id="winback"><div class="kicker">Win-backs</div>
<h2>Winning back lost deals is a rounding error</h2>
{table(['', *[YL[y] for y in Y]], [
 ['Funded new deals'] + [K(WB[int(y)]['funded']) for y in Y],
 ['&hellip;whose business had an earlier lost or declined new opp (win-back)'] + [K(WB[int(y)]['winback']) for y in Y],
 ['Win-back share of funded deals'] + [P(WB[int(y)]['winback_share'], 1) for y in Y],
 ['Win-back share of funded dollars'] + [P(WB[int(y)]['winback_amt_share'], 1) for y in Y],
 ['Funded deals with &ldquo;Deal Lost&rdquo; as the lead source'] + [K(WB[int(y)]['deal_lost_src']) for y in Y],
 ['&hellip;share of funded deals'] + [P(WB[int(y)]['deal_lost_src_share'], 1) for y in Y],
 ['Opps created from the Deal-Lost distributor queue'] + [K(DLS[y]['opps']) for y in Y],
], foot='Win-back = the funded deal&rsquo;s account had a previous new-business opp that ended Closed Lost or Declined (going back to 2021).')}
<div class="plain"><b>What it means.</b> About 1 in 100 funded deals is a win-back, and the dedicated &ldquo;Deal Lost&rdquo; queue has nearly disappeared (137 funded in 2024, 27 so far in 2026). With roughly 20,000 approved-but-lost deals a year now, this is an untouched pile.</div>
</section>
""")

# ===== Seasonality =====
mn = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
def sea(k):
    d = R[k]; return [d.get(str(i), d.get(f'{i}.0', d.get(f'{float(i)}'))) for i in range(1, 13)]
add(f"""
<section id="season"><div class="kicker">Seasons</div>
<h2>The second half of the year is 20&ndash;40% stronger than the first</h2>
<div class="plain">Seasonality index for 2023&ndash;2025: 1.00 = an average month for that year. Above 1 is a strong month; below 1 is weak. 2026 is left out because it is not a full year.</div>
{bar_chart(mn, [('Leads assigned', [v*100 for v in sea('season_assigned')]), ('Opps created', [v*100 for v in sea('season_opps')]), ('Deals funded', [v*100 for v in sea('season_funded')]), ('Dollars funded', [v*100 for v in sea('season_funded_amt')])], yfmt=lambda v: f"{v:.0f}", h=280, value_labels=False, note='Index by calendar month, 100 = average month. Average of 2023, 2024 and 2025.')}
<div class="plain"><b>What it means.</b> February through May run at about 80&ndash;90% of an average month. October and December are the peaks (dollars funded 124% and 132%). Plan hiring so new reps are ramped by July, and do not read a weak March as a problem.</div>
</section>
""")

# ===== Lenders =====
LF, LS = R['lender_funded_conc'], R['lender_sub_conc']
def top5(d, y): return ', '.join(f"{t['lender']} {P(t['share'])}" for t in d[y]['top'][:5])
add(f"""
<section id="lenders"><div class="kicker">Lenders</div>
<h2>Submissions are spread wider; fundings lean harder on On Deck</h2>
{table(['Funded deals by lender', *[YL[y] for y in Y]], [
 ['Lenders that funded at least one deal'] + [K(LF[y]['lenders_used']) for y in Y],
 ['Top lender share of funded deals'] + [P(LF[y]['top1_share']) for y in Y],
 ['Top 5 lenders share'] + [P(LF[y]['top5_share']) for y in Y],
 ['Top 10 lenders share'] + [P(LF[y]['top10_share']) for y in Y],
 ['Concentration score (HHI)'] + [K(LF[y]['hhi']) for y in Y],
 ['Top 5'] + [top5(LF, y) for y in Y],
], foot='HHI = sum of squared shares; under 1,500 counts as unconcentrated. Headway was #1 in 2023–24, fell to #3 in 2025 and out of the top 8 in 2026. On Deck, Forward Financing, Expansion and Byzfunder now fund half of all deals.')}
{table(['Lender submissions', *[YL[y] for y in Y]], [
 ['Submissions per month'] + [K(R['subs_per_opp_mavg'][y]) for y in Y],
 ['Submissions per submitted opp'] + [K(R['subs_per_submitted_opp'][y], 1) for y in Y],
 ['Lenders receiving submissions'] + [K(LS[y]['lenders']) for y in Y],
 ['Top lender share of submissions'] + [P(LS[y]['top1_share'])  for y in Y],
 ['Top 10 lenders share of submissions'] + [P(LS[y]['top10_share']) for y in Y],
 ['Concentration score (HHI)'] + [K(LS[y]['hhi']) for y in Y],
], foot='Each opp is now shopped to almost 12 lenders, up from 8. Submissions are spread across 49–52 lenders.')}
{hbar([(t['lender'], t['share']*100) for t in LF['2026']['top'][:8]], vfmt=lambda v: f"{v:.0f}%", color='var(--y26)', note='Share of funded deals by lender, 2026 (Jan–Aug).')}
<div class="plain"><b>What it means.</b> No single lender is dangerous yet (the top one funds under a fifth of deals), but the funding mix is drifting toward On Deck while submissions are being sprayed wider and wider. Shopping every deal to 12 lenders costs rep time and lender goodwill; the approval rate went up, but close-on-approvals went down, which hints that more offers are not turning into more funded deals.</div>
</section>
""")

# ===== Why deals die =====
LR, DR = R['lost_reasons_year'], R['decline_reasons_year']
def top_reasons(d, y, n=6):
    return sorted(d[y].items(), key=lambda t: -t[1])[:n]
lr26 = top_reasons(LR, '2026', 7)
dr26 = top_reasons(DR, '2026', 7)
def reason_rows(d, keys):
    tot = {y: sum(d[y].values()) for y in Y}
    return [[H.escape(k)] + [P(d[y].get(k, 0) / tot[y]) if tot[y] else '–' for y in Y] + [K(d['2026'].get(k, 0))] for k in keys]
add(f"""
<section id="why"><div class="kicker">Why deals die</div>
<h2>&ldquo;Did not like the offer&rdquo; and &ldquo;lost contact&rdquo; are two-thirds of closed-lost</h2>
<div class="two">
<div><h3>Closed lost (after approval)</h3>{table(['Reason', *[f'{YS[y]} share' for y in Y], '2026 count'], reason_rows(LR, [k for k, _ in lr26]))}</div>
<div><h3>Declined (by lenders)</h3>{table(['Reason', *[f'{YS[y]} share' for y in Y], '2026 count'], reason_rows(DR, [k for k, _ in dr26]))}</div>
</div>
<div class="plain"><b>What it means.</b> &ldquo;Lost contact with merchant&rdquo; grew from {P(LR['2023']['Lost Contact w/ Merchant']/sum(LR['2023'].values()))} to {P(LR['2026']['Lost Contact w/ Merchant']/sum(LR['2026'].values()))} of closed-lost deals, and is now {K(LR['2026']['Lost Contact w/ Merchant'])} deals in eight months. That is a process problem (follow-up speed, too many leads per rep, new reps), not a market problem. On the decline side, &ldquo;volume too low&rdquo; and &ldquo;poor cash flow&rdquo; are 40% of declines, which points back at lead quality.</div>
</section>
""")

# ===== Verdict =====
add(f"""
<section id="verdict"><div class="kicker">The verdict</div>
<h2>Strengths, weaknesses, trends, and problems</h2>
<div class="sw">
<div class="box good"><h3>Strengths</h3><ul>
<li>Scale: 3.3x the funded deals and 3.8x the dollars of 2023, every month.</li>
<li>Lender approval rate up from 53% to 59%; lender base is wide (40+ funding, 50 receiving submissions).</li>
<li>Deal size up 17% to $57K; the $100K+ share of fundings rose from 12% to 18%.</li>
<li>Partner sources (Sofi, Bluevine, On Deck, merchant referrals) convert 2&ndash;3x better than bought leads and are growing.</li>
<li>Smarter routing: size tiers put the biggest businesses (32% of leads) with converting reps.</li>
<li>Less dependence on stars: the top 20% of reps carry 35% of fundings, down from 49%.</li>
</ul></div>
<div class="box bad"><h3>Weaknesses</h3><ul>
<li>No productivity gain per rep in four years: about 9 funded and $43K revenue per AE per month, flat.</li>
<li>Close on approvals fell every year (30% &rarr; 26%); closed-lost now eats 62% of approvals.</li>
<li>Bought-lead quality is falling: businessloans.com and Fundera lead-to-opp roughly halved; sub-580 credit is 31% of opps.</li>
<li>SBG&rsquo;s take per funded dollar fell from 9.05% to 8.04%.</li>
<li>Only 60% of created leads reach a new-business rep (was 74%).</li>
<li>Win-back and deal-lost recycling is essentially unused (about 1% of fundings).</li>
</ul></div>
<div class="box soft"><h3>Emerging trends</h3><ul>
<li>Revenue-share leads went from 15% to 49% of opps and close better than paid leads.</li>
<li>Headcount is now outrunning leads: AEs up 34% on 2025, assigned leads up 6%; leads per rep fell under 200 in mid-2026.</li>
<li>Submissions per deal climbed from 8 to 12; lender mix shifting to On Deck / Forward / Expansion; Headway faded out.</li>
<li>Longer tails: average lead-to-funded time doubled even though typical deals are as fast as ever.</li>
<li>Bigger tiers and bigger products (term loans up to 16% of fundings) are pushing deal size up.</li>
</ul></div>
<div class="box warn"><h3>Problems to fix first</h3><ul>
<li><b>The post-approval leak.</b> &ldquo;Lost contact&rdquo; is 4x 2023 and &ldquo;did not like the approval&rdquo; is 44% of losses. Set a same-day-offer rule, track time from approval to first contact, and give new reps scripted offer presentation.</li>
<li><b>New-rep ramp.</b> Reps under 3 months close 14% vs 17&ndash;18% for veterans, and the three new-hire managers run 25&ndash;45% below the pack. Ramp is the manager gap.</li>
<li><b>Lead buying.</b> Re-price businessloans.com and Fundera against $47&ndash;65 revenue per lead; shift budget toward Sofi/Bluevine-type partnerships worth $120&ndash;565 per lead.</li>
<li><b>Low-tier leads.</b> Sub-580 credit, under-$200K revenue and Tier 1 leads close 5&ndash;9%. Route them to a cheaper path (VSS-style or automated) instead of AEs.</li>
<li><b>Headcount pacing.</b> Tie hiring to assigned-lead growth; at today&rsquo;s lead flow, more reps mostly means fewer leads each.</li>
</ul></div>
</div>
</section>
""")

# ===== Data notes =====
add(f"""
<section id="notes"><div class="kicker">Data notes</div>
<h2>How the numbers were built</h2>
<ul class="note">
<li><b>Period.</b> Calendar years 2023, 2024, 2025 and January&ndash;August 2026. Every yearly figure is the monthly average for that window; September 2026 (partial) is excluded.</li>
<li><b>New business only.</b> Opportunities with Type = New. Leads routed to the Renewals distribution team (about 18&ndash;19K unique per year in 2025&ndash;26) are excluded from assigned counts. Leads created cannot be perfectly split, so about 5% of 2025&ndash;26 &ldquo;leads created&rdquo; are existing customers.</li>
<li><b>Leads assigned.</b> From Distribution Engine logs (n2de__Distribution_log__c), counting each lead once per calendar month, with the Renewals team excluded. The lead-report &ldquo;ever assigned&rdquo; share is shown separately for comparison.</li>
<li><b>Funnel rates.</b> Approved = Approved flag, a Pre-Approved date, or a stage of Pre-Approved / Contracts / Funded. Funded = Funded stage with a funded date; funded dollars use Funded Amount; SBG revenue uses the SBG Revenue field. Approval bands use Largest Approval (Max Approval is empty on every record).</li>
<li><b>Headcount.</b> AEs = users with the Sales Rep or Sales Rep - Manager profile who received at least 10 unique leads in the month. VSS = Sales Rep - VSS profile.</li>
<li><b>Managers.</b> The Distribution Engine&rsquo;s Assigned User Manager stamp exists from November 2024. Each rep-month is credited to the manager who received most of that rep&rsquo;s leads that month; deals are credited by the opp&rsquo;s creation month. Adam Block (VSS and onboarding pool), Jake Rotman (VP pool), and ops users are shown but not ranked. 2023 has only Team Jake / Team Adam stamps.</li>
<li><b>Distribution Teams 1&ndash;7</b> are lead tiers (the same reps are members of every tier), not manager teams.</li>
<li><b>Sales cycle.</b> Lead assigned &rarr; opp uses the opp&rsquo;s first-assigned date to its created date; opp &rarr; funded uses created to funded date. Medians are the &ldquo;typical&rdquo; deal; means include the long tail.</li>
<li><b>Seasonality.</b> Average of each month&rsquo;s share of its own year&rsquo;s total, 2023&ndash;2025.</li>
<li><b>Win-back.</b> Funded deal whose account had an earlier new opp ending Closed Lost or Declined (2021 onward).</li>
</ul>
</section>
</div>
""")

html = ''.join(parts)
out = f'{S}/out/new_business_story.html'
open(out, 'w').write(html)
print(out, len(html))
