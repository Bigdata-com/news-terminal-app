"""
Sector (theme) topic templates for non-entity news searches.

Unlike ``config.topics``, these phrases contain **no** ``{company}`` placeholder:
sector searches run against the Bigdata.com Search API without an entity filter,
so the phrase text is sent verbatim as the semantic query.

Each topic is a ``{"topic_name", "topic_text"}`` pair. ``topic_name`` doubles as
the filter-tab label in the web UI, so several phrases may share one name.
"""

from __future__ import annotations

from typing import Any, TypeAlias

SectorTopic: TypeAlias = dict[str, str]
Sector: TypeAlias = dict[str, Any]


# Web UI uses this to replace stale sector topics in localStorage. Increment **every** time
# you add/remove/reorder/edit entries in any sector's topic list (or change which desks are enabled/labeled).
SECTOR_TOPICS_REVISION: int = 3


def safe_sector_topics_revision() -> int:
    """Return ``SECTOR_TOPICS_REVISION`` as an int >= 1 for API consumers."""
    try:
        revision = int(SECTOR_TOPICS_REVISION)
    except (TypeError, ValueError):
        return 1
    return revision if revision >= 1 else 1


# ── ENERGY ───────────────────────────────────────────────────────────────────
# Desk-specific guidance for AI query expansion. A generic "reword this query" prompt
# produces synonym swaps; naming the desk's benchmarks, venues and units makes the
# variations retrieve genuinely different documents instead of near-duplicates.
ENERGY_EXPANSION_PROMPT: str = """You are a crude oil and refined products desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: Brent, WTI, Dubai and Murban benchmarks; OPEC+ quotas, compliance and \
spare capacity; contango, backwardation, time spreads and the forward curve; crack spreads, distillate \
and gasoline cracks; refinery turnarounds, run cuts and utilisation rates; VLCC, Suezmax and Aframax \
freight rates and tanker day rates; the Strait of Hormuz, Red Sea, Bab el-Mandeb, Suez and Panama \
canals; EIA, IEA and OPEC monthly reports and inventory draws or builds at Cushing and the ARA hub; \
LNG cargoes, TTF and Henry Hub, JKM and regasification; sanctions, price caps, shadow fleet and \
ship-to-ship transfers; FIDs, licensing rounds, upstream capex and decline rates.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between price action, physical flows, \
policy decisions, positioning and company or trader commentary
- Prefer the specific benchmark, region, grade, hub or institution over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


# Google-style phrasing: keyword-dense natural language, no company placeholder.
ENERGY_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Crude Prices",
        "topic_text": "Brent and WTI crude oil prices rise or fall on shifting supply and demand outlook",
    },
    {
        "topic_name": "OPEC+ Policy",
        "topic_text": "OPEC+ ministers agree to raise cut or extend crude production quotas",
    },
    {
        "topic_name": "Supply Disruption",
        "topic_text": "unplanned oil field outage pipeline shutdown or export terminal disruption halts crude supply",
    },
    {
        "topic_name": "Inventories",
        "topic_text": "weekly US crude oil and gasoline inventories build or draw in EIA petroleum status report",
    },
    {
        "topic_name": "Refining",
        "topic_text": "refinery outage maintenance turnaround or unplanned shutdown tightens refined product supply",
    },
    {
        "topic_name": "Product Cracks",
        "topic_text": "diesel gasoline and jet fuel crack spreads and distillate stock levels move on demand",
    },
    {
        "topic_name": "Sanctions",
        "topic_text": "sanctions on Russian and Iranian crude exports price cap enforcement and shadow fleet tankers",
    },
    {
        "topic_name": "Geopolitical Risk",
        "topic_text": "Middle East conflict Strait of Hormuz and Red Sea attacks threaten tanker traffic and oil flows",
    },
    {
        "topic_name": "Demand Outlook",
        "topic_text": "IEA OPEC and EIA revise global oil demand growth forecasts for the year",
    },
    {
        "topic_name": "Freight and Tankers",
        "topic_text": "crude tanker freight rates and VLCC earnings surge as shipping routes shift",
    },
    {
        "topic_name": "Gas and LNG",
        "topic_text": "European TTF and US Henry Hub natural gas prices move on LNG cargo flows and storage levels",
    },
    {
        "topic_name": "Positioning",
        "topic_text": "hedge funds and managed money shift net length in crude futures as the curve moves into contango or backwardation",
    },
    {
        "topic_name": "Upstream Investment",
        "topic_text": "upstream capital spending licensing round and final investment decision on new oil and gas project",
    },
    {
        "topic_name": "Weather Outages",
        "topic_text": "hurricane or extreme cold disrupts Gulf of Mexico oil production and Gulf Coast refining",
    },
    {
        "topic_name": "Policy and Transition",
        "topic_text": "government energy policy emissions rules and transition targets reshape oil and gas investment",
    },
]


# ── METALS & MINING ──────────────────────────────────────────────────────────
METALS_MINING_EXPANSION_PROMPT: str = """You are a metals and mining desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: LME, SHFE, COMEX and Dalian contracts; LME and Shanghai bonded \
warehouse stocks, cancelled warrants, cash-to-three-month spreads; iron ore 62% Fe and 65% Fe \
indices, coking coal and Newcastle thermal coal; HRC and rebar prices, blast furnace versus EAF \
economics, steel mill margins and scrap spreads; copper concentrate treatment and refining charges \
(TC/RC), smelter maintenance and closures; aluminium P1020 and Midwest premium, alumina and bauxite, \
smelter power costs; nickel Class 1, NPI and MHP, lithium carbonate and spodumene, cobalt hydroxide, \
NdPr and rare earth quotas; gold and silver ETF holdings, central bank buying, COMEX net length; \
AISC and C1 cash costs, head grade, strip ratio, reserve replacement, JORC and NI 43-101 resource \
statements, PEA, feasibility studies and FIDs; force majeure, tailings dam failure, mill outage, \
labour strike and community blockade; royalty and windfall taxes, export bans, permit revocation and \
resource nationalism in Indonesia, Chile, Peru, Mexico and the DRC; Section 232 tariffs, \
anti-dumping duties, quotas and CBAM; offtake and streaming agreements.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between price action, mine and smelter \
supply, cost curves, policy and permitting, exchange inventories and positioning, and corporate \
capital allocation
- Prefer the specific metal, exchange, index, mine, region or institution over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


METALS_MINING_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Copper Prices",
        "topic_text": "LME and COMEX copper prices rise or fall on warehouse inventories and Chinese demand",
    },
    {
        "topic_name": "Iron Ore & Steel",
        "topic_text": "iron ore 62% Fe index and Chinese steel mill margins move on blast furnace output and rebar demand",
    },
    {
        "topic_name": "Precious Metals",
        "topic_text": "gold and silver prices move on central bank buying ETF holdings and real interest rates",
    },
    {
        "topic_name": "Battery Metals",
        "topic_text": "lithium carbonate spodumene cobalt and nickel prices track electric vehicle and battery demand",
    },
    {
        "topic_name": "Aluminium & Alumina",
        "topic_text": "LME aluminium alumina and bauxite prices move on smelter power costs and regional premiums",
    },
    {
        "topic_name": "Mine Disruption",
        "topic_text": "labour strike accident community blockade or force majeure halts output at a major mine",
    },
    {
        "topic_name": "Smelter & Refining",
        "topic_text": "smelter closures maintenance and copper concentrate treatment and refining charges tighten refined metal supply",
    },
    {
        "topic_name": "Cost Inflation",
        "topic_text": "rising all-in sustaining costs falling head grades and labour energy inflation squeeze miner margins",
    },
    {
        "topic_name": "Mining M&A",
        "topic_text": "mining takeover bid asset sale joint venture or hostile approach reshapes producer portfolios",
    },
    {
        "topic_name": "Project Pipeline",
        "topic_text": "feasibility study final investment decision and capital cost overrun on new mine or expansion project",
    },
    {
        "topic_name": "Resource Nationalism",
        "topic_text": "government raises mining royalties and taxes bans ore exports or revokes permits for mine owners",
    },
    {
        "topic_name": "Exploration & Reserves",
        "topic_text": "drill results resource upgrade and reserve replacement at exploration and development projects",
    },
    {
        "topic_name": "Tariffs & Trade Policy",
        "topic_text": "metal import tariffs quotas anti-dumping duties and carbon border adjustment reshape trade flows",
    },
    {
        "topic_name": "Critical Minerals",
        "topic_text": "rare earth and critical mineral export controls government stockpiles and supply chain funding",
    },
    {
        "topic_name": "Stocks & Positioning",
        "topic_text": "LME SHFE and COMEX warehouse stocks time spreads and managed money positioning in base metals",
    },
]


# ── UTILITIES & POWER ────────────────────────────────────────────────────────
UTILITIES_POWER_EXPANSION_PROMPT: str = """You are a utilities and power desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: PJM, ERCOT, MISO, CAISO, SPP, ISO-NE and NYISO markets; day-ahead \
and real-time LMPs, congestion, negative prices, ancillary services and scarcity pricing; capacity \
auctions, clearing prices, reserve margins and loss-of-load expectation; heat rate, spark and dark \
spreads; EPEX, Nord Pool and EEX baseload power, CfD and contract-for-difference auctions; rate \
cases before state commissions and the PUCT, allowed ROE, rate base, riders and trackers, FERC \
orders, Ofgem RIIO price controls and RAB models; integrated resource plans, interconnection queue \
reform, transmission buildout and grid capex; hyperscaler data centre load growth, large-load \
interconnection, PPAs, colocation and behind-the-meter deals; nuclear uprates, licence extensions, \
restarts, SMRs and the production tax credit; solar wind and battery storage additions, ITC and PTC \
safe harbour, tax equity and curtailment; coal retirements, gas peakers and CCGTs, fuel hedging and \
purchased power costs; wildfire liability, inverse condemnation, storm restoration and securitised \
cost recovery; EPA rules, RGGI, EU ETS and carbon allowance prices; drought and hydro output, \
heatwave and cold-snap demand, conservation appeals and grid emergency alerts.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between wholesale price action, load \
growth, regulatory and rate decisions, generation and grid capex, fuel costs and reliability events
- Prefer the specific ISO, regulator, technology, region or auction over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


UTILITIES_POWER_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Power Prices",
        "topic_text": "wholesale electricity prices rise or fall in power markets on demand tight supply and fuel costs",
    },
    {
        "topic_name": "Capacity Auctions",
        "topic_text": "capacity auction clearing prices reserve margins and resource adequacy shortfalls in PJM and ISO markets",
    },
    {
        "topic_name": "Grid Reliability",
        "topic_text": "heatwave or winter storm strains the grid triggering conservation appeals emergency alerts and rolling blackouts",
    },
    {
        "topic_name": "Data Center Demand",
        "topic_text": "data centre load growth large-load interconnection requests and power purchase agreements with hyperscalers",
    },
    {
        "topic_name": "Rate Cases",
        "topic_text": "state regulators approve or reject utility rate increases allowed return on equity and rate base additions",
    },
    {
        "topic_name": "Transmission Buildout",
        "topic_text": "transmission line approvals interconnection queue reform and grid capital spending plans",
    },
    {
        "topic_name": "Nuclear",
        "topic_text": "nuclear reactor uprates licence extensions restarts and small modular reactor orders",
    },
    {
        "topic_name": "Renewables Buildout",
        "topic_text": "solar and wind capacity additions offshore wind auctions tax credits and project cancellations",
    },
    {
        "topic_name": "Battery Storage",
        "topic_text": "utility-scale battery storage procurement installations and grid-scale energy storage economics",
    },
    {
        "topic_name": "Coal & Gas Fleet",
        "topic_text": "coal plant retirement or life extension and new gas peaker and combined cycle plant orders",
    },
    {
        "topic_name": "Fuel & Hedging",
        "topic_text": "natural gas and coal fuel costs spark spreads and purchased power expense pass-through for generators",
    },
    {
        "topic_name": "Wildfire & Storms",
        "topic_text": "wildfire liability claims hurricane restoration costs and securitised storm cost recovery for utilities",
    },
    {
        "topic_name": "Utility M&A",
        "topic_text": "utility takeover minority stake sale in transmission or renewables and infrastructure fund investment",
    },
    {
        "topic_name": "Policy & Carbon",
        "topic_text": "emissions rules carbon allowance prices and clean energy mandates reshape generation investment",
    },
    {
        "topic_name": "Hydro & Weather",
        "topic_text": "drought reservoir levels and hydro generation shortfalls shift power supply and weather-driven demand",
    },
]


# ── SHIPPING & FREIGHT ───────────────────────────────────────────────────────
SHIPPING_FREIGHT_EXPANSION_PROMPT: str = """You are a shipping and freight desk analyst writing \
search queries for a real-time news feed.

Useful vocabulary for this desk: Baltic Dry Index, Capesize 5TC, Panamax, Supramax and Handysize \
average earnings; BDTI and BCTI dirty and clean tanker indices, Worldscale, TCE earnings, VLCC, \
Suezmax, Aframax, LR2 and MR tonnage; SCFI, WCI, FBX and Xeneta container spot rates on \
transpacific and Asia-Europe lanes, general rate increases, peak season surcharges, blank sailings, \
idle fleet, capacity discipline and alliance reshuffles; period time charter fixtures, secondhand \
asset values, newbuild orderbook to fleet ratio, yard slots, deliveries and demolition; port \
congestion, terminal dwell times, chassis shortages and dockworker strikes; Suez and Red Sea \
diversions around the Cape of Good Hope, Houthi attacks, war risk premiums, Panama Canal draft \
restrictions and transit slots; sanctions, dark and shadow fleet tankers, ship-to-ship transfers \
and OFAC designations; IMO net-zero framework and carbon levy, EU ETS for shipping, FuelEU \
Maritime, CII and EEXI ratings, scrubbers and LNG methanol and ammonia dual-fuel newbuilds; VLSFO \
and MGO bunker prices and the Hi-5 spread; ton-mile demand for iron ore grain coal and containers; \
air cargo yields and the TAC and Baltic Air Freight indices; US truckload spot rates, tender \
rejections, LTL pricing, intermodal volumes and AAR rail carloads.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between freight rate action, vessel \
supply and ordering, trade volumes and routing, regulation and fuel costs, and disruption events
- Prefer the specific index, vessel class, lane, canal, port or regulator over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


SHIPPING_FREIGHT_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Dry Bulk Rates",
        "topic_text": "Baltic Dry Index and Capesize Panamax daily earnings rise or fall on iron ore coal and grain cargoes",
    },
    {
        "topic_name": "Tanker Rates",
        "topic_text": "crude and product tanker rates VLCC Suezmax and MR time charter equivalent earnings move on cargo demand",
    },
    {
        "topic_name": "Container Rates",
        "topic_text": "container spot freight rates on transpacific and Asia to Europe lanes move on capacity and blank sailings",
    },
    {
        "topic_name": "Chokepoints",
        "topic_text": "Red Sea diversions around the Cape of Good Hope Suez transits and Panama Canal draft restrictions reroute trade",
    },
    {
        "topic_name": "Port Congestion",
        "topic_text": "port congestion terminal dwell times and dockworker strike disrupt container handling and inland logistics",
    },
    {
        "topic_name": "Fleet Supply",
        "topic_text": "newbuild orderbook shipyard slots vessel deliveries scrapping and idle fleet reshape shipping capacity",
    },
    {
        "topic_name": "Charter & Asset Values",
        "topic_text": "period time charter fixtures and secondhand vessel asset values signal owner expectations",
    },
    {
        "topic_name": "Trade Volumes",
        "topic_text": "global container throughput grain coal and iron ore shipments shift ton-mile demand",
    },
    {
        "topic_name": "Tariffs & Trade Policy",
        "topic_text": "tariffs port fees and trade policy changes pull forward or destroy seaborne cargo volumes",
    },
    {
        "topic_name": "Sanctions & Dark Fleet",
        "topic_text": "sanctioned tankers shadow fleet ship-to-ship transfers and OFAC designations reshape tanker trades",
    },
    {
        "topic_name": "Decarbonisation Rules",
        "topic_text": "IMO carbon levy EU emissions trading for shipping FuelEU and carbon intensity ratings raise compliance costs",
    },
    {
        "topic_name": "Bunker Fuel",
        "topic_text": "VLSFO and marine gasoil bunker prices scrubber spreads and LNG methanol ammonia bunkering uptake",
    },
    {
        "topic_name": "Air Freight",
        "topic_text": "air cargo rates yields and bellyhold capacity shift on e-commerce demand and cross-border volumes",
    },
    {
        "topic_name": "Trucking & Rail",
        "topic_text": "truckload spot rates tender rejections less-than-truckload pricing and rail carload and intermodal volumes",
    },
    {
        "topic_name": "Marine Casualty",
        "topic_text": "vessel collision grounding fire piracy attack and rising war risk and hull insurance premiums",
    },
]


# ── FINANCE ──────────────────────────────────────────────────────────────────
FINANCE_EXPANSION_PROMPT: str = """You are a banks and capital markets desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: net interest income and margin, deposit betas, funding costs, \
brokered CDs and DDA mix shift, FHLB advances and discount window borrowing; loan growth in C&I, \
CRE and NDFI lending; asset quality metrics such as net charge-offs, nonaccruals, criticised loans, \
CECL reserve builds and allowance coverage; CET1, Basel III endgame, the stress capital buffer, \
CCAR and DFAST results, SLR and G-SIB surcharges, AOCI and held-to-maturity marks, buybacks and \
dividend increases; SOFR, repo market pressure, the standing repo facility, the reverse repo \
facility, quantitative tightening and FOMC decisions, dot plots and the 2s10s curve; FICC and \
equities trading revenue, prime brokerage balances, investment banking fees, ECM, DCM and M&A \
advisory league tables; AUM net flows, ETF flows, fee compression, private credit and direct \
lending spreads, BDC marks, PIK income, dry powder, secondaries and continuation vehicles; \
high-yield and investment-grade spreads, leveraged loan and CLO issuance; card and auto \
delinquencies, FICO migration and subprime losses; payments volumes, interchange, stablecoins and \
BNPL; OCC, FDIC, Federal Reserve and CFPB enforcement, consent orders and AML penalties; regional \
bank mergers and deal approvals.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between rate and macro policy, balance \
sheet and funding, credit quality, fee and trading revenue, capital return, regulation and deals
- Prefer the specific metric, market, regulator or institution over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


FINANCE_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Rates & Fed Policy",
        "topic_text": "Federal Reserve rate decision dot plot and yield curve shifts reset the outlook for bank earnings",
    },
    {
        "topic_name": "Net Interest Margin",
        "topic_text": "banks guide net interest income and margin higher or lower on deposit betas and asset repricing",
    },
    {
        "topic_name": "Deposits & Funding",
        "topic_text": "deposit outflows brokered CD costs FHLB advances and repo market pressure raise bank funding costs",
    },
    {
        "topic_name": "Credit Quality",
        "topic_text": "banks report rising loan losses charge-offs bad loans and higher provisions for credit losses",
    },
    {
        "topic_name": "Consumer Credit",
        "topic_text": "credit card delinquencies subprime auto losses and household debt stress rise among lower income borrowers",
    },
    {
        "topic_name": "Commercial Real Estate",
        "topic_text": "office and multifamily commercial real estate loan maturities defaults and appraisal writedowns hit lenders",
    },
    {
        "topic_name": "Capital & Stress Tests",
        "topic_text": "CET1 ratios Basel endgame rules stress test results and share buyback and dividend approvals",
    },
    {
        "topic_name": "Trading Revenue",
        "topic_text": "fixed income currencies commodities and equities trading revenue swing with market volatility and client activity",
    },
    {
        "topic_name": "Capital Markets Fees",
        "topic_text": "investment banking fees rebound as IPO pipeline debt issuance and merger advisory mandates recover",
    },
    {
        "topic_name": "Private Credit",
        "topic_text": "private credit and direct lending spreads business development company marks and PIK income raise concerns",
    },
    {
        "topic_name": "Credit Spreads",
        "topic_text": "high yield and investment grade credit spreads leveraged loan and CLO issuance signal risk appetite",
    },
    {
        "topic_name": "Fund Flows",
        "topic_text": "asset and wealth manager net flows ETF inflows and fee compression reshape assets under management",
    },
    {
        "topic_name": "Bank M&A",
        "topic_text": "regional bank merger agreements branch sales and regulatory approval of bank deals",
    },
    {
        "topic_name": "Regulation & Fines",
        "topic_text": "banking regulators issue consent orders anti-money laundering penalties and new supervisory rules",
    },
    {
        "topic_name": "Payments & Fintech",
        "topic_text": "payment volumes interchange rules stablecoin adoption and buy now pay later lending shift financial services",
    },
]


# ── TECHNOLOGY ───────────────────────────────────────────────────────────────
TECHNOLOGY_EXPANSION_PROMPT: str = """You are a technology sector desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: hyperscaler capital expenditure guidance, AI accelerator and GPU \
supply, HBM stacks, CoWoS and advanced packaging capacity, foundry nodes such as N3 and N2, wafer \
starts, foundry utilisation, wafer fab equipment spending and SEMI billings; DRAM and NAND contract \
prices, ASPs, lead times and inventory corrections; BIS export controls, entity list additions, \
chip licence approvals and Section 301 tariffs; cloud revenue growth, backlog and remaining \
performance obligations, consumption versus seat-based pricing; SaaS ARR, cRPO, net revenue \
retention, churn, billings and Rule of 40; digital ad spend, CPMs, retail media and return on ad \
spend; smartphone and PC unit shipments, replacement cycles and ODM production shifts; data centre \
power constraints, liquid cooling, colocation vacancy and interconnection; frontier model releases, \
inference and token pricing, agents and open-weight models; antitrust cases at the DOJ and FTC, the \
EU Digital Markets Act, the AI Act, privacy rules and app store regulation; zero-day exploitation, \
ransomware, data breaches and critical CVEs; take-privates, sponsor deals and the tech IPO window; \
restructuring, layoffs and operating margin discipline.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between AI infrastructure spending, \
semiconductor supply and pricing, software and cloud demand, end-market units, policy and \
security, and corporate capital allocation
- Prefer the specific technology, node, index, regulator, benchmark or end market over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


TECHNOLOGY_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "AI Capex",
        "topic_text": "hyperscalers raise capital spending guidance on AI data centre buildout and accelerator purchases",
    },
    {
        "topic_name": "AI Model Launches",
        "topic_text": "frontier AI model release inference cost declines and token pricing reshape the competitive landscape",
    },
    {
        "topic_name": "Semiconductor Cycle",
        "topic_text": "chip orders book-to-bill foundry utilisation and inventory correction signal the semiconductor cycle turning",
    },
    {
        "topic_name": "Memory Pricing",
        "topic_text": "DRAM and NAND contract prices and high bandwidth memory supply tighten on AI server demand",
    },
    {
        "topic_name": "Chip Equipment",
        "topic_text": "wafer fab equipment spending lithography tool orders and new fab construction and subsidies",
    },
    {
        "topic_name": "Export Controls",
        "topic_text": "semiconductor export controls entity list additions and chip licence restrictions on China sales",
    },
    {
        "topic_name": "Cloud Growth",
        "topic_text": "cloud revenue growth rates backlog and remaining performance obligations show enterprise AI workload adoption",
    },
    {
        "topic_name": "Software Demand",
        "topic_text": "enterprise software spending scrutiny seat growth and recurring revenue guidance for SaaS vendors",
    },
    {
        "topic_name": "Digital Advertising",
        "topic_text": "digital advertising spend CPMs and retail media growth shift budgets across platforms",
    },
    {
        "topic_name": "Devices & Supply Chain",
        "topic_text": "smartphone and PC shipments replacement cycles component shortages and contract manufacturing shifts",
    },
    {
        "topic_name": "Data Center Power",
        "topic_text": "data centre power constraints liquid cooling adoption and colocation vacancy limit AI capacity growth",
    },
    {
        "topic_name": "Antitrust & Regulation",
        "topic_text": "antitrust lawsuits Digital Markets Act enforcement and AI and privacy regulation target large technology platforms",
    },
    {
        "topic_name": "Cybersecurity",
        "topic_text": "exploited zero-day vulnerability ransomware attack and large data breach disrupt enterprise operations",
    },
    {
        "topic_name": "Tech M&A & IPOs",
        "topic_text": "technology take-private sponsor buyout and IPO window reopening for venture backed companies",
    },
    {
        "topic_name": "Margins & Layoffs",
        "topic_text": "technology restructuring headcount cuts and operating expense discipline defend operating margins",
    },
]


# ── INSURANCE ────────────────────────────────────────────────────────────────
INSURANCE_EXPANSION_PROMPT: str = """You are an insurance and reinsurance desk analyst writing \
search queries for a real-time news feed.

Useful vocabulary for this desk: net written premium growth, renewal rate change, combined loss and \
expense ratios, accident year ex-catastrophe loss ratio and loss cost trend; insured catastrophe \
loss estimates from PCS, PERILS, Verisk and RMS for hurricanes, severe convective storms, \
wildfires, floods and earthquakes; January 1, April 1 and July 1 reinsurance renewals, property \
catastrophe rate-on-line, retentions and attachment points, quota share and retrocession, \
catastrophe bond issuance and spreads, sidecars and collateralised reinsurance, insurance-linked \
securities capacity; probable maximum loss, one-in-100 year return periods, AM Best ratings and \
risk-based capital; prior-year reserve development, social inflation, nuclear verdicts, litigation \
funding, commercial auto and umbrella casualty deterioration; excess and surplus lines growth, \
managing general agents, fronting carriers and delegated authority; personal auto and homeowners \
rate filings, frequency and severity trends, Florida and California availability, FAIR Plan and \
Citizens depopulation; annuity and pension risk transfer sales, spread compression, Bermuda and \
offshore asset-intensive reinsurance and NAIC scrutiny of private credit in general accounts; \
medical loss ratios, utilisation trend, Medicare Advantage rate notices, star ratings and risk \
adjustment; new money investment yields and alternatives income; cyber premium growth and \
ransomware losses; broker organic growth and insurance M&A.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between catastrophe losses, pricing and \
renewal cycles, reserves and loss trends, capital and alternative capacity, regulation and \
availability, and life health and investment income drivers
- Prefer the specific peril, renewal date, line of business, regulator or metric over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


INSURANCE_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Cat Losses",
        "topic_text": "insured catastrophe loss estimates from hurricane wildfire flood and severe convective storm events",
    },
    {
        "topic_name": "Hurricane Season",
        "topic_text": "hurricane season forecasts landfall risk and modelled loss scenarios for property insurers",
    },
    {
        "topic_name": "Pricing Cycle",
        "topic_text": "commercial property and casualty renewal rate change decelerates as the market softens",
    },
    {
        "topic_name": "Reinsurance Renewals",
        "topic_text": "January and mid-year reinsurance renewals set property catastrophe rate-on-line retentions and attachment points",
    },
    {
        "topic_name": "Cat Bonds & ILS",
        "topic_text": "catastrophe bond issuance spreads and insurance-linked securities and sidecar capacity inflows",
    },
    {
        "topic_name": "Reserve Development",
        "topic_text": "adverse prior-year reserve development and reserve strengthening in long tail casualty lines",
    },
    {
        "topic_name": "Social Inflation",
        "topic_text": "nuclear verdicts litigation funding and rising loss cost trend in commercial auto and umbrella casualty",
    },
    {
        "topic_name": "E&S and Specialty",
        "topic_text": "excess and surplus lines premium growth managing general agents and fronting carrier capacity",
    },
    {
        "topic_name": "Personal Lines",
        "topic_text": "personal auto and homeowners rate filings claims frequency and severity and margin recovery",
    },
    {
        "topic_name": "State Regulation",
        "topic_text": "state insurance regulators address homeowners availability rate approvals and residual market depopulation",
    },
    {
        "topic_name": "Life & Annuities",
        "topic_text": "annuity sales pension risk transfer deals spread compression and offshore asset-intensive reinsurance",
    },
    {
        "topic_name": "Health Insurers",
        "topic_text": "medical loss ratios utilisation trend Medicare Advantage rate notices and risk adjustment pressure health insurers",
    },
    {
        "topic_name": "Cyber Insurance",
        "topic_text": "cyber insurance premium growth ransomware claims severity and systemic cyber accumulation risk",
    },
    {
        "topic_name": "Investment Income",
        "topic_text": "insurers report higher new money yields alternative investment income and private credit allocations",
    },
    {
        "topic_name": "Insurance M&A",
        "topic_text": "insurance and reinsurance mergers broker consolidation and Bermuda carrier capital raises",
    },
]


# Ordered registry driving the sector tile grid. Disabled sectors are omitted from
# ``list_sectors()`` (hidden in the UI) and cannot be searched until re-enabled.
SECTORS: list[Sector] = [
    {
        "id": "energy",
        "label": "Energy",
        "description": "Crude, refined products, gas and LNG, freight and policy",
        "enabled": True,
        "topics": ENERGY_TOPICS,
        "expansion_prompt": ENERGY_EXPANSION_PROMPT,
    },
    {
        "id": "utilities_power",
        "label": "Power",
        "description": "Power prices, grid capacity and generation mix",
        "enabled": True,
        "topics": UTILITIES_POWER_TOPICS,
        "expansion_prompt": UTILITIES_POWER_EXPANSION_PROMPT,
    },
    {
        "id": "shipping_freight",
        "label": "Shipping & Freight",
        "description": "Dry bulk, container rates and trade route shifts",
        "enabled": True,
        "topics": SHIPPING_FREIGHT_TOPICS,
        "expansion_prompt": SHIPPING_FREIGHT_EXPANSION_PROMPT,
    },
    {
        "id": "metals_mining",
        "label": "Metals",
        "description": "Base and precious metals, mine supply and processing",
        "enabled": True,
        "topics": METALS_MINING_TOPICS,
        "expansion_prompt": METALS_MINING_EXPANSION_PROMPT,
    },
    {
        "id": "finance",
        "label": "Finance",
        "description": "Banks, rates, credit quality and capital markets",
        "enabled": False,
        "topics": FINANCE_TOPICS,
        "expansion_prompt": FINANCE_EXPANSION_PROMPT,
    },
    {
        "id": "technology",
        "label": "Technology",
        "description": "AI capex, semis, cloud and software demand",
        "enabled": False,
        "topics": TECHNOLOGY_TOPICS,
        "expansion_prompt": TECHNOLOGY_EXPANSION_PROMPT,
    },
    {
        "id": "insurance",
        "label": "Insurance",
        "description": "Catastrophes, pricing cycle, reserves and reinsurance",
        "enabled": False,
        "topics": INSURANCE_TOPICS,
        "expansion_prompt": INSURANCE_EXPANSION_PROMPT,
    },
]


class UnknownSectorError(ValueError):
    """Raised when a sector id is unknown or not enabled for search."""


def get_sector(sector_id: str) -> Sector:
    """
    Look up an enabled sector by id.

    Args:
        sector_id: Sector identifier (case-insensitive), e.g. ``"energy"``

    Returns:
        The sector definition including its topic list

    Raises:
        UnknownSectorError: If the id is unknown or the sector is not enabled
    """
    key = sector_id.strip().lower()
    for sector in SECTORS:
        if sector["id"] == key:
            if not sector["enabled"]:
                raise UnknownSectorError(f"Sector '{sector_id}' is not available yet")
            return sector

    available = ", ".join(s["id"] for s in SECTORS if s["enabled"])
    raise UnknownSectorError(f"Unknown sector '{sector_id}'. Available: {available}")


def get_sector_expansion_prompt(sector_id: str) -> str:
    """
    Return the AI query-expansion prompt for a sector.

    Falls back to a generic sector prompt so expansion still works for a sector that
    has topics but no bespoke desk guidance yet.

    Args:
        sector_id: Sector identifier (case-insensitive)

    Raises:
        UnknownSectorError: If the id is unknown or the sector is not enabled
    """
    sector = get_sector(sector_id)
    prompt = (sector.get("expansion_prompt") or "").strip()
    if prompt:
        return prompt

    return (
        f"You are a {sector['label']} sector analyst writing search queries for a real-time news feed. "
        "Shift the angle of each variation rather than only swapping synonyms, prefer specific "
        "benchmarks, regions and institutions over generic wording, and keep every variation a "
        "self-contained query about the sector rather than about one named company."
    )


def list_sectors() -> list[Sector]:
    """Return tile metadata for enabled sectors only (disabled desks stay hidden)."""
    return [
        {
            "id": sector["id"],
            "label": sector["label"],
            "description": sector["description"],
            "enabled": sector["enabled"],
            "topic_count": len(sector["topics"]),
        }
        for sector in SECTORS
        if sector["enabled"]
    ]


def default_topics_by_sector() -> dict[str, list[SectorTopic]]:
    """Return default topic lists keyed by sector id (enabled sectors only)."""
    return {sector["id"]: sector["topics"] for sector in SECTORS if sector["enabled"]}
