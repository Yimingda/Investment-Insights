"""追踪的重要人物名单 —— 自由增删即可。

每条字段：
  name   显示名（中文/英文皆可）
  en     GDELT 英文检索词（人名 + 可选机构，提升命中）
  cat    类别（见 CATEGORIES）
  handle X(推特) 用户名，无公开账号填 None
  stance 背后立场 / 利益（"屁股决定脑袋"，由身份与利益结构推导，供打折扣参考）
"""

AI_LEAD = "AI 领军"
FED = "美联储 / 美国政要"
CENBANK = "各国央行"
MARKET = "市场大佬 / 投资人"
CRYPTO = "加密 KOL"

CATEGORIES = [AI_LEAD, FED, CENBANK, MARKET, CRYPTO]

PEOPLE = [
    # ── AI 领军 / 高影响力 ──
    {"name": "Sam Altman", "en": "Sam Altman OpenAI", "cat": AI_LEAD, "handle": "sama",
     "stance": "OpenAI CEO，靠持续融资+算力扩张 → 倾向渲染 AGI 临近、AI 需求无上限以撑估值；对开源/监管的立场随 OpenAI 利益摇摆。"},
    {"name": "黄仁勋 Jensen Huang", "en": "Jensen Huang Nvidia", "cat": AI_LEAD, "handle": None,
     "stance": "Nvidia CEO，AI 算力最大卖方，股价与 AI 资本开支直接绑定 → 几乎永远看多 AI 需求（买越多省越多），淡化泡沫与竞争风险。"},
    {"name": "Elon Musk", "en": "Elon Musk", "cat": AI_LEAD, "handle": "elonmusk",
     "stance": "横跨 Tesla/xAI/SpaceX/X，言论服务自身资产与政治影响力 → 看多自家（自驾/Grok），抨击对手与监管；常兼具拉盘与政治意图。"},
    {"name": "Sundar Pichai", "en": "Sundar Pichai Google", "cat": AI_LEAD, "handle": "sundarpichai",
     "stance": "Google CEO，核心利益是搜索广告现金牛不被 AI 颠覆 → 强调全栈 AI 实力与追赶叙事，淡化搜索被替代风险。"},
    {"name": "Satya Nadella", "en": "Satya Nadella Microsoft", "cat": AI_LEAD, "handle": "satyanadella",
     "stance": "Microsoft CEO，深绑 OpenAI + Azure 云 → 力推「AI 即生产力 / Copilot」，利益在企业云算力消费上升。"},
    {"name": "Dario Amodei", "en": "Dario Amodei Anthropic", "cat": AI_LEAD, "handle": None,
     "stance": "Anthropic CEO，既要融资又打「安全」差异化 → 强调 AI 能力强+风险大（双刃：既证明实力又抬高监管门槛利好头部）。"},
    {"name": "Demis Hassabis", "en": "Demis Hassabis DeepMind", "cat": AI_LEAD, "handle": "demishassabis",
     "stance": "DeepMind CEO，科学声誉 + Google 资源 → 偏重科研突破叙事（蛋白质/科学），相对克制商业炒作。"},

    # ── 美联储 / 美国政要 ──
    {"name": "Kevin Warsh (美联储主席)", "en": "Kevin Warsh Federal Reserve", "cat": FED, "handle": None,
     "stance": "特朗普提名的新主席，鹰派出身却需配合政府 → 市场最关注其独立性是否让位于政治性降息/弱美元诉求。"},
    {"name": "Jerome Powell (美联储理事/前主席)", "en": "Jerome Powell Federal Reserve", "cat": FED, "handle": None,
     "stance": "已卸任主席、留任理事，捍卫美联储独立性与自身历史评价 → 倾向强调数据依赖、抵制政治干预。"},
    {"name": "Donald Trump", "en": "Donald Trump", "cat": FED, "handle": "realDonaldTrump",
     "stance": "利益=政绩+股市+低利率 → 持续施压美联储降息、唱多经济、以关税为筹码；言论服务政治叙事。"},
    {"name": "Scott Bessent (财长)", "en": "Scott Bessent Treasury", "cat": FED, "handle": None,
     "stance": "财长，代表政府财政利益 → 力挺弱美元/低利率/国债顺利发行，淡化赤字与通胀担忧。"},
    {"name": "Christopher Waller (Fed)", "en": "Christopher Waller Federal Reserve", "cat": FED, "handle": None,
     "stance": "Fed 理事、被视为潜在主席人选 → 近期偏鸽、倾向支持降息，立场与上位预期相关。"},
    {"name": "John Williams (NY Fed)", "en": "John Williams New York Fed", "cat": FED, "handle": None,
     "stance": "纽约联储主席、体制内核心、偏中性 → 维护美联储框架与渐进路线，发言谨慎少惊喜。"},

    # ── 各国央行行长 ──
    {"name": "Christine Lagarde (ECB)", "en": "Christine Lagarde ECB", "cat": CENBANK, "handle": "Lagarde",
     "stance": "ECB 行长、政治家出身，维护欧元区团结与欧元信誉 → 措辞平衡、强调通胀目标，避免分裂南北欧。"},
    {"name": "植田和男 Kazuo Ueda (BOJ)", "en": "Kazuo Ueda Bank of Japan", "cat": CENBANK, "handle": None,
     "stance": "BOJ 行长，背负数十年宽松「退出」重任 → 极谨慎：既怕加息刺破日债/日元，又怕通胀失控，倾向渐进与模糊。"},
    {"name": "潘功胜 Pan Gongsheng (PBoC)", "en": "Pan Gongsheng PBoC", "cat": CENBANK, "handle": None,
     "stance": "央行行长，服务稳增长+稳汇率+防风险三角 → 措辞官方、宽松有度，首要避免人民币与地产系统性风险。"},
    {"name": "Andrew Bailey (BOE)", "en": "Andrew Bailey Bank of England", "cat": CENBANK, "handle": None,
     "stance": "BOE 行长，夹在高通胀与弱增长之间 → 立场偏谨慎防御，常被批反应偏慢。"},

    # ── 市场大佬 / 知名投资人 ──
    {"name": "Warren Buffett", "en": "Warren Buffett Berkshire", "cat": MARKET, "handle": None,
     "stance": "Berkshire，坐拥巨额现金的价值投资旗手 → 口头唱多美国长期，但行动（囤现金/减持）常比言论更诚实。"},
    {"name": "Ray Dalio", "en": "Ray Dalio Bridgewater", "cat": MARKET, "handle": "RayDalio",
     "stance": "Bridgewater，卖「宏观范式/债务周期」叙事 → 长期看空美债/美元、唱多分散与黄金，立场服务其宏观品牌。"},
    {"name": "Bill Ackman", "en": "Bill Ackman Pershing", "cat": MARKET, "handle": "BillAckman",
     "stance": "Pershing，集中持仓+公开喊话影响标的 → 发言常为其多空头寸服务（talking his book），政治表态亦高调。"},
    {"name": "Cathie Wood", "en": "Cathie Wood ARK Invest", "cat": MARKET, "handle": "CathieDWood",
     "stance": "ARK，重仓高估值颠覆式成长股 → 几乎永远看多科技（Tesla/AI/比特币），需维持叙事以吸引申购。"},
    {"name": "Jamie Dimon", "en": "Jamie Dimon JPMorgan", "cat": MARKET, "handle": None,
     "stance": "JPMorgan，银行业龙头 → 既唱多美国韧性又反复预警风险（对冲），维护银行与监管话语权。"},
    {"name": "Larry Fink", "en": "Larry Fink BlackRock", "cat": MARKET, "handle": None,
     "stance": "BlackRock，全球最大资管 → 力推 ETF/私募/比特币 ETF 与「长期配置」，立场服务 AUM 增长。"},

    # ── 加密 KOL ──
    {"name": "CZ (赵长鹏)", "en": "Changpeng Zhao Binance", "cat": CRYPTO, "handle": "cz_binance",
     "stance": "币安创始人、持有大量加密资产 → 永远看多加密采用，淡化监管与中心化风险。"},
    {"name": "Vitalik Buterin", "en": "Vitalik Buterin Ethereum", "cat": CRYPTO, "handle": "VitalikButerin",
     "stance": "以太坊精神领袖，声誉绑定 ETH 生态 → 偏技术理想主义、看多去中心化，相对克制价格炒作。"},
    {"name": "Brian Armstrong", "en": "Brian Armstrong Coinbase", "cat": CRYPTO, "handle": "brian_armstrong",
     "stance": "Coinbase CEO，上市交易所利益在交易量与合规化 → 力推加密入主流+友好监管，看多采用。"},
    {"name": "Michael Saylor", "en": "Michael Saylor Strategy", "cat": CRYPTO, "handle": "saylor",
     "stance": "Strategy 公司杠杆重仓比特币 → 极端看多 BTC（「数字黄金」），言论几乎是其持仓的布道。"},
]


# 推荐候选（默认不追踪，可在"管理人员"页一键添加）
CANDIDATES = [
    # AI 领军
    {"name": "Mark Zuckerberg", "en": "Mark Zuckerberg Meta", "cat": AI_LEAD, "handle": None,
     "stance": "Meta CEO，押注开源 AI（Llama）+ 元宇宙 → 力推开源以削弱对手闭源优势，看多 AI 算力投入。"},
    {"name": "Mira Murati", "en": "Mira Murati AI", "cat": AI_LEAD, "handle": None,
     "stance": "前 OpenAI CTO 自立门户、需融资 → 倾向 AI 能力乐观叙事，立场服务新公司估值。"},
    {"name": "Andrej Karpathy", "en": "Andrej Karpathy AI", "cat": AI_LEAD, "handle": "karpathy",
     "stance": "独立教育者（前特斯拉/OpenAI），利益绑定较少 → 偏工程视角、相对中立，少商业立场。"},
    # 美联储 / 美国政要
    {"name": "JD Vance (副总统)", "en": "JD Vance Vice President", "cat": FED, "handle": "JDVance",
     "stance": "副总统，政治利益绑定特朗普议程 → 唱多本届经济政策、抨击对手阵营。"},
    {"name": "Austan Goolsbee (Chicago Fed)", "en": "Austan Goolsbee Federal Reserve", "cat": FED, "handle": None,
     "stance": "芝加哥联储、偏鸽学者型 → 倾向支持降息、更看重就业一侧。"},
    {"name": "Neel Kashkari (Minneapolis Fed)", "en": "Neel Kashkari Federal Reserve", "cat": FED, "handle": None,
     "stance": "明尼阿波利斯联储、直言且立场常摇摆 → 随通胀数据在鹰鸽间切换。"},
    # 各国央行
    {"name": "Joachim Nagel (Bundesbank)", "en": "Joachim Nagel Bundesbank", "cat": CENBANK, "handle": None,
     "stance": "德国央行行长、传统鹰派 → 强调反通胀纪律，警惕过快宽松。"},
    {"name": "Tiff Macklem (BoC)", "en": "Tiff Macklem Bank of Canada", "cat": CENBANK, "handle": None,
     "stance": "加拿大央行行长、小型开放经济 → 紧盯美联储与加元，偏务实跟随。"},
    # 市场大佬 / 投资人
    {"name": "Stanley Druckenmiller", "en": "Stanley Druckenmiller", "cat": MARKET, "handle": None,
     "stance": "顶级宏观交易员 → 立场随持仓灵活，公开宏观大判断（美债/AI）常服务其交易。"},
    {"name": "Howard Marks", "en": "Howard Marks Oaktree", "cat": MARKET, "handle": None,
     "stance": "Oaktree 信用/周期大师 → 偏防御、强调风险与周期位置，卖「备忘录」智慧品牌。"},
    {"name": "Ken Griffin", "en": "Ken Griffin Citadel", "cat": MARKET, "handle": None,
     "stance": "Citadel 做市+对冲巨头、亦是政治金主 → 维护市场结构与自身业务，偏理性看多美国资本市场。"},
    # 加密 KOL
    {"name": "Arthur Hayes", "en": "Arthur Hayes BitMEX", "cat": CRYPTO, "handle": "CryptoHayes",
     "stance": "BitMEX 创始人、重仓加密+宏观博主 → 看多加密/看空法币，言论服务其持仓与「流动性」框架。"},
    {"name": "Justin Sun 孙宇晨", "en": "Justin Sun Tron", "cat": CRYPTO, "handle": "justinsuntron",
     "stance": "Tron 创始人、持有大量加密+营销驱动 → 极度看多自家生态，争议多，需辨别炒作成分。"},
]


def by_categories(cats):
    return [p for p in PEOPLE if p["cat"] in cats]
