#!/usr/bin/env python3
"""Generate a deterministic sample file tree for a sample company (Codelibs, Inc.).

The tree mixes Japanese and English documents in txt, md, html, csv, json, pdf,
docx, xlsx, pptx and png formats, nested up to six directories deep, with varied
sizes, modification times spread over about three years, and file or folder
names that contain spaces, Japanese and other characters that need URL
encoding. Only the Python 3 standard library is used. Every name, company and
figure is made up.

Output is reproducible: content and modification times depend only on --seed
and --reference-date (default: a fixed date, so every run gives the same tree).
"""

import argparse
import datetime as dt
import calendar
import csv
import io
import json
import os
import random
import struct
import sys
import textwrap
import zipfile
import zlib
from xml.sax.saxutils import escape as xml_escape

DEFAULT_SEED = 20260930
DEFAULT_REFERENCE_DATE = "2026-09-30"

MONTH_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"]

# ---------------------------------------------------------------------------
# Fictional vocabulary
# ---------------------------------------------------------------------------

REGIONS = [("East Japan", "東日本"), ("West Japan", "西日本"), ("Overseas", "海外")]
CUSTOMERS = [("Silverline Foods", "シルバーライン食品"), ("Aoba Logistics", "青葉ロジスティクス"),
             ("Hoshino Trading Co., Ltd", "星野商事株式会社"), ("Blue Heron Supplies", "ブルーヘロン商会"),
             ("Kawasemi Works", "かわせみ製作所"), ("Tsubame Travel", "つばめトラベル")]
VENDORS = [("Harbor Cloud Services", "ハーバークラウドサービス"), ("Granite Office Supply", "グラナイト事務機器"),
           ("Lantern Security", "ランタンセキュリティ"), ("Sora Print Studio", "空印刷スタジオ")]
PRODUCTS = ["Cedar Suite", "Maple Gateway", "Willow Analytics", "Birch Connect", "Ginkgo Backup"]
PROJECTS = [("Project Maple", "プロジェクト・メイプル", "maple-gateway"),
            ("Project Cedar", "プロジェクト・シーダー", "cedar-suite"),
            ("Willow Platform", "ウィロー基盤", "willow-analytics")]
CAMPAIGNS = [("Spring Launch", "春の新製品"), ("Partner Webinar Series", "パートナーウェビナー"),
             ("Year-End Appreciation", "年末感謝")]
DEPT_TEAMS = {
    "Sales": ("Sales Operations", "営業企画"),
    "Engineering": ("Platform Engineering", "プラットフォーム開発"),
    "HR": ("People Team", "人事"),
    "Finance": ("Finance and Accounting", "経理財務"),
    "Legal": ("Legal Affairs", "法務"),
    "Marketing": ("Marketing Communications", "マーケティング"),
    "Shared": ("Office Services", "オフィスサービス"),
    "GA": ("General Affairs", "総務部"),
}

# (English, Japanese) document titles per department.
TOPICS = {
    "Sales": [("Monthly Sales Report", "月次営業報告"), ("Account Plan", "アカウントプラン"),
              ("Quarterly Pipeline Review", "四半期パイプラインレビュー"), ("Customer Proposal", "提案書"),
              ("Meeting Notes", "商談メモ"), ("Pricing Guidelines", "価格ガイドライン")],
    "Engineering": [("Design Document", "設計書"), ("Release Notes", "リリースノート"), ("Runbook", "運用手順書"),
                    ("Incident Report", "障害報告書"), ("API Reference", "APIリファレンス"),
                    ("Test Plan", "テスト計画書"), ("Architecture Overview", "アーキテクチャ概要")],
    "HR": [("Onboarding Guide", "入社ガイド"), ("Remote Work Policy", "リモートワーク規程"),
           ("Training Plan", "研修計画"), ("Recruiting Status", "採用状況"),
           ("Performance Review Guide", "評価ガイド"), ("Benefits Overview", "福利厚生の概要")],
    "Finance": [("Budget", "予算"), ("Expense Report", "経費報告"), ("Forecast", "業績予測"),
                ("Audit Summary", "監査サマリー"), ("Cost Review", "コストレビュー")],
    "Legal": [("Master Services Agreement", "基本取引契約書"), ("Non-Disclosure Agreement", "秘密保持契約書"),
              ("Privacy Policy", "プライバシーポリシー"), ("Compliance Checklist", "コンプライアンスチェックリスト"),
              ("Vendor Contract Summary", "取引先契約の概要")],
    "Marketing": [("Campaign Plan", "キャンペーン計画"), ("Brand Guidelines", "ブランドガイドライン"),
                  ("Web Analytics Summary", "Web解析サマリー"), ("Press Release", "プレスリリース"),
                  ("Content Calendar", "コンテンツカレンダー")],
    "Shared": [("Employee Handbook", "社員ハンドブック"), ("Meeting Notes", "会議メモ"),
               ("Office Announcement", "社内のお知らせ"), ("Document Template", "文書テンプレート"),
               ("FAQ", "よくある質問")],
    "GA": [("Internal Regulations", "社内規程"), ("Meeting Minutes", "議事録"),
           ("Equipment Register", "備品管理台帳"), ("Fire Drill Notice", "防災訓練のご案内")],
}

# Sentence templates (English, Japanese) per department.
BANK = {
    "Sales": (
        ["Revenue in the {region} region reached {amount} million yen in {month}, {pct}% above the plan.",
         "{customer} renewed its annual subscription and added {n} seats.",
         "Pipeline coverage for the next quarter stands at {n}x the target, led by mid-market deals.",
         "The win rate improved by {pct} points after the new discovery checklist was introduced.",
         "Action: the account team will schedule an executive review with {customer} before the end of {month}.",
         "Discounts above {pct}% require approval from the regional sales director.",
         "Forecast accuracy for {month} was within {pct}% of the committed number."],
        ["{month}の{region}地域の売上は{amount}百万円となり、計画比{pct}%増となりました。",
         "{customer}は年間契約を更新し、{n}ライセンスを追加しました。",
         "次四半期のパイプラインは目標の{n}倍を確保しており、中堅企業向けの案件が中心です。",
         "新しいヒアリングシートの導入により、受注率が{pct}ポイント改善しました。",
         "対応事項：営業チームは{month}末までに{customer}との役員レビューを設定します。",
         "{pct}%を超える値引きには、地域営業責任者の承認が必要です。",
         "{month}の予測精度は、コミット数値に対して{pct}%以内に収まりました。"]),
    "Engineering": (
        ["{proj} {ver} adds a retry policy for upstream calls and reduces p95 latency by {pct}%.",
         "The service runs on {n} nodes behind the internal load balancer; rolling updates keep availability above 99.9%.",
         "Operators must check the health endpoint before and after every deployment of {proj}.",
         "Root cause: a misconfigured connection pool exhausted database connections during the {month} batch window.",
         "Mitigation: the pool size was raised to {n}, and an alert now fires when utilization exceeds {pct}%.",
         "All public endpoints require token authentication, and request payloads are validated against the published schema.",
         "The nightly regression suite for {proj} must pass before a release candidate is tagged."],
        ["{proj} {ver} では上流サービス呼び出しに再試行ポリシーを導入し、p95レイテンシを{pct}%短縮しました。",
         "本サービスは社内ロードバランサ配下の{n}ノードで稼働し、ローリングアップデートにより可用性99.9%以上を維持します。",
         "運用担当者は{proj}をデプロイする前後に、必ずヘルスチェックエンドポイントを確認してください。",
         "原因：{month}のバッチ処理時間帯に、コネクションプールの設定不備によりデータベース接続が枯渇しました。",
         "対策：プールサイズを{n}に増やし、使用率が{pct}%を超えるとアラートが発報されるようにしました。",
         "公開エンドポイントはすべてトークン認証が必須で、リクエストは公開済みスキーマに照らして検証されます。",
         "{proj}の夜間リグレッションテストが成功することが、リリース候補をタグ付けする条件です。"]),
    "HR": (
        ["New hires receive their equipment and account credentials on the first day, and a buddy is assigned for the first {n} weeks.",
         "Employees may work remotely up to {n} days per week with the approval of their manager.",
         "The recruiting team reviewed {n} applications in {month}; {pct}% advanced to the first interview.",
         "Annual training covers information security, harassment prevention, and data protection.",
         "Performance reviews are held twice a year and focus on goals, growth, and feedback from peers.",
         "Benefits include health checkups, a commuting allowance, and a learning budget of {amount},000 yen per year.",
         "Questions about leave, payroll, or benefits can be sent to the HR help desk."],
        ["新入社員には初日に機器とアカウント情報が渡され、最初の{n}週間はバディが付きます。",
         "従業員は、上長の承認を得て、週{n}日までリモートワークができます。",
         "採用チームは{month}に{n}件の応募を確認し、{pct}%が一次面接に進みました。",
         "年次研修では、情報セキュリティ、ハラスメント防止、個人情報保護を扱います。",
         "人事評価は年2回実施され、目標、成長、同僚からのフィードバックを重視します。",
         "福利厚生には、健康診断、通勤手当、年間{amount},000円の学習支援が含まれます。",
         "休暇、給与、福利厚生に関するご質問は、人事ヘルプデスクまでお寄せください。"]),
    "Finance": (
        ["Operating expenses for {month} were {amount} million yen, {pct}% below the approved budget.",
         "Expense reports must be submitted within {n} business days and include itemized receipts.",
         "The forecast for Q{quarter} assumes stable demand and a {pct}% increase in cloud infrastructure costs.",
         "Capital purchases above {amount},000 yen require approval from the finance director.",
         "The external audit found no material issues; two minor recommendations concern document retention.",
         "Travel costs decreased as more customer meetings moved online.",
         "Accruals are reviewed on the fifth business day of each month."],
        ["{month}の営業費用は{amount}百万円で、承認済み予算を{pct}%下回りました。",
         "経費精算は{n}営業日以内に、明細付きの領収書を添えて提出してください。",
         "Q{quarter}の見通しは、需要が安定し、クラウド基盤費用が{pct}%増加することを前提としています。",
         "{amount},000円を超える資産購入には、経理部長の承認が必要です。",
         "外部監査では重要な指摘事項はなく、書類保管に関する軽微な提言が2件ありました。",
         "顧客との打ち合わせがオンラインに移行したため、出張費は減少しました。",
         "未払計上は毎月5営業日目に確認されます。"]),
    "Legal": (
        ["This agreement takes effect on the date of signature and renews automatically for successive one-year terms.",
         "Each party shall keep the other party's confidential information secret for {n} years after termination.",
         "Personal data is processed only for the purposes stated in this policy and is retained no longer than necessary.",
         "Vendors must complete the security questionnaire before a contract with {vendor} can be signed.",
         "Any amendment must be made in writing and signed by authorized representatives of both parties.",
         "The compliance checklist is reviewed every quarter by the legal team and the information security team.",
         "Disputes will be resolved through good-faith negotiation before any formal proceedings begin."],
        ["本契約は署名日より効力を生じ、1年ごとに自動的に更新されるものとします。",
         "各当事者は、契約終了後{n}年間、相手方の秘密情報を秘密として保持するものとします。",
         "個人情報は本ポリシーに定める目的の範囲でのみ取り扱い、必要な期間を超えて保管しません。",
         "{vendor}との契約を締結する前に、取引先はセキュリティ質問票に回答する必要があります。",
         "契約の変更は書面により行い、双方の権限ある代表者が署名するものとします。",
         "コンプライアンスチェックリストは、法務部と情報セキュリティ部が四半期ごとに見直します。",
         "紛争が生じた場合は、正式な手続に入る前に、誠実な協議による解決を図ります。"]),
    "Marketing": (
        ["The {campaign} campaign generated {n},000 visits to the landing page, with a conversion rate of {pct}%.",
         "Email open rates rose after subject lines were shortened and tailored by industry.",
         "Brand guidelines require clear space around the primary logo equal to the height of the mark.",
         "Social media engagement was strongest on posts that told real customer stories.",
         "The press release will be sent to trade media in {month} and posted on the corporate site.",
         "Paid search spend was {amount},000 yen in {month}, with a cost per lead {pct}% lower than the previous period.",
         "The content calendar for the next quarter focuses on case studies, webinars, and product tutorials."],
        ["{campaign}キャンペーンでは、ランディングページへの訪問が{n},000件、コンバージョン率は{pct}%でした。",
         "件名を短くし、業種ごとに出し分けたことで、メールの開封率が上昇しました。",
         "ブランドガイドラインでは、プライマリロゴの周囲にロゴの高さと同じ余白を確保することが求められます。",
         "ソーシャルメディアでは、お客様の実際の事例を紹介した投稿の反応が最も良好でした。",
         "プレスリリースは{month}に業界メディアへ配信し、コーポレートサイトにも掲載します。",
         "{month}の検索広告費は{amount},000円で、リード単価は前期比{pct}%低下しました。",
         "来四半期のコンテンツカレンダーは、導入事例、ウェビナー、製品チュートリアルを中心に構成します。"]),
    "Shared": (
        ["The office will be closed on {month} {day} for the annual facility inspection.",
         "Please use the shared calendar to reserve meeting rooms and avoid double bookings.",
         "Visitors must register at the reception desk and wear a visitor badge while in the building.",
         "The monthly all-hands meeting is held on the first Monday and recorded for those who cannot attend.",
         "Report suspicious emails to the IT help desk and do not click links or open attachments.",
         "Templates for documents, spreadsheets, and presentations are available in the Templates folder.",
         "Meeting notes should list the decisions made, the owners, and the due date of each action item."],
        ["{month}{day}日は年次設備点検のため、オフィスを閉鎖します。",
         "会議室の予約は共有カレンダーを使用し、二重予約を避けてください。",
         "来訪者は受付で登録し、館内では来訪者用のバッジを着用してください。",
         "月例の全社会議は第1月曜日に開催し、参加できない方のために録画を共有します。",
         "不審なメールを受け取った場合は、ITヘルプデスクに報告し、リンクや添付ファイルを開かないでください。",
         "文書、表計算、プレゼンテーションのテンプレートは、テンプレートフォルダにあります。",
         "議事録には、決定事項、担当者、各アクションの期限を記載してください。"]),
    "GA": (
        ["Changes to the work rules are announced to all employees in {month} after consultation with staff representatives.",
         "Equipment purchases are approved within {n} business days after a request form is sent to General Affairs.",
         "A fire drill is held {n} times a year, and all employees are expected to take part.",
         "Please confirm the venue and budget with General Affairs before planning a company event.",
         "Mail and parcels are received at the front desk and handed over within {n} hours.",
         "The office key register is checked at the end of every month, and any loss must be reported immediately.",
         "Meeting minutes are written by the next business day and shared with all attendees."],
        ["就業規則の改定は、従業員代表との協議を経て、{month}に全社へ周知されます。",
         "備品の購入は、購入申請書を総務部に提出後、{n}営業日以内に承認されます。",
         "防災訓練は年{n}回実施し、全従業員の参加を原則とします。",
         "社内イベントを企画する際は、事前に会場と予算を総務部に確認してください。",
         "郵便物と宅配便は受付で受け取り、{n}時間以内に担当者へお渡しします。",
         "オフィスの鍵の管理簿は毎月末に確認し、紛失があれば直ちに報告します。",
         "議事録は会議の翌営業日までに作成し、出席者全員に共有します。"]),
}

HEADINGS = (["Summary", "Background", "Details", "Findings", "Decisions", "Action Items", "Next Steps", "Notes"],
            ["概要", "背景", "詳細", "所見", "決定事項", "対応事項", "今後の予定", "備考"])

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc(year, month, day, hour=0, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def epoch(when):
    return calendar.timegm(when.utctimetuple())


def rand_bytes(rng, n):
    return rng.getrandbits(8 * n).to_bytes(n, "little") if n else b""


def is_ascii(text):
    return all(ord(c) < 128 for c in text)


class Ctx:
    """Everything a renderer needs to know about one file."""

    def __init__(self, rng, dept, lang, when, proj=None, region=None, customer=None, vendor=None, campaign=None):
        self.rng = rng
        self.dept = dept
        self.lang = lang  # "en", "ja" or "mix"
        self.when = when
        self.proj = proj or rng.choice(PROJECTS)
        self.region = region or rng.choice(REGIONS)
        self.customer = customer or rng.choice(CUSTOMERS)
        self.vendor = vendor or rng.choice(VENDORS)
        self.campaign = campaign or rng.choice(CAMPAIGNS)

    @property
    def team(self):
        return DEPT_TEAMS[self.dept]

    def slots(self, lang):
        i = 0 if lang == "en" else 1
        rng = self.rng
        month = MONTH_EN[self.when.month - 1] if lang == "en" else "%d月" % self.when.month
        return {
            "proj": self.proj[i], "region": self.region[i], "customer": self.customer[i], "vendor": self.vendor[i],
            "campaign": self.campaign[i], "month": month, "day": rng.randint(1, 28), "n": rng.randint(2, 40),
            "pct": rng.randint(2, 35), "amount": rng.randint(8, 480), "ver": "v%d.%d.%d" % (
                rng.randint(1, 4), rng.randint(0, 12), rng.randint(0, 9)),
            "quarter": (self.when.month - 1) // 3 + 1,
        }


def sentence(ctx, lang):
    bank = BANK[ctx.dept][0 if lang == "en" else 1]
    return ctx.rng.choice(bank).format(**ctx.slots(lang))


def paragraph(ctx, lang, count):
    return [sentence(ctx, lang) for _ in range(count)]


def join_sentences(sentences):
    return "".join(sentences) if not sentences[0][:1].isascii() else " ".join(sentences)


class Doc:
    def __init__(self, title, lang, team, when, sections, table=None):
        self.title = title
        self.lang = lang
        self.team = team
        self.when = when
        self.sections = sections  # [(heading, [[sentence, ...], ...]), ...]
        self.table = table  # (headers, rows) or None

    def paragraphs(self):
        for heading, paras in self.sections:
            yield heading, [join_sentences(p) for p in paras]


# size class -> (sections, min paragraphs per section, max paragraphs per section)
SIZES = {"small": (3, 1, 2), "medium": (8, 3, 5), "large": (40, 5, 8), "xl": (160, 5, 8)}


def build_doc(ctx, topic, size):
    """Create the abstract content of a document for the given topic and size class."""
    rng, lang = ctx.rng, ctx.lang
    sections_n, lo, hi = SIZES[size]
    if size == "small":
        sections_n = rng.randint(2, 3)
    elif size == "medium":
        sections_n = rng.randint(5, 9)
    en_title, ja_title = topic
    when = ctx.when
    date_en = "%s %d, %d" % (MONTH_EN[when.month - 1], when.day, when.year)
    date_ja = "%d年%d月%d日" % (when.year, when.month, when.day)
    if lang == "en":
        title = "%s - %s" % (en_title, date_en)
    elif lang == "ja":
        title = "%s（%s）" % (ja_title, date_ja)
    else:
        title = "%s / %s" % (en_title, ja_title)
    sections = []
    for i in range(sections_n):
        h_idx = i % len(HEADINGS[0])
        if lang == "en":
            heading = HEADINGS[0][h_idx]
        elif lang == "ja":
            heading = HEADINGS[1][h_idx]
        else:
            heading = "%s / %s" % (HEADINGS[0][h_idx], HEADINGS[1][h_idx])
        if sections_n > len(HEADINGS[0]):
            heading += " %d" % (i // len(HEADINGS[0]) + 1)
        paras = []
        for j in range(rng.randint(lo, hi)):
            plang = lang if lang != "mix" else ("en" if (i + j) % 2 == 0 else "ja")
            paras.append(paragraph(ctx, plang, rng.randint(2, 4)))
        sections.append((heading, paras))
    table = None
    if size != "small" or rng.random() < 0.4:
        headers, rows = dataset(ctx, rng.randint(3, 6), "ja" if lang == "ja" else "en")
        table = (headers, [[fmt_cell(v) for v in row] for row in rows])
    team = ctx.team[1] if lang == "ja" else ctx.team[0]
    return Doc(title, lang, team, when, sections, table)


def fmt_cell(v):
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float):
        return "%.1f" % v
    if isinstance(v, int):
        return "{:,}".format(v) if abs(v) >= 10000 else str(v)
    return str(v)


# ---------------------------------------------------------------------------
# Tabular data
# ---------------------------------------------------------------------------


def rand_date(ctx, i=0):
    return (ctx.when - dt.timedelta(days=ctx.rng.randint(0, 85))).date()


def dataset(ctx, rows, hlang):
    """Return (headers, rows) with typed values (str, int, float, date) for the department."""
    rng = ctx.rng
    ja = hlang == "ja"
    d = ctx.dept
    pick = rng.choice
    if d == "Sales":
        cols = [("Date", "日付", lambda: rand_date(ctx)), ("Region", "地域", lambda: pick(REGIONS)[1 if ja else 0]),
                ("Customer", "顧客", lambda: pick(CUSTOMERS)[1 if ja else 0]), ("Product", "製品", lambda: pick(PRODUCTS)),
                ("Quantity", "数量", lambda: rng.randint(1, 200)),
                ("Amount (JPY)", "金額（円）", lambda: rng.randint(30, 9000) * 1000)]
    elif d == "Engineering":
        cols = [("Build", "ビルド", lambda: "build-%05d" % rng.randint(1000, 99999)), ("Date", "日付", lambda: rand_date(ctx)),
                ("Service", "サービス", lambda: pick(PROJECTS)[2]), ("Result", "結果", lambda: pick(["passed", "passed", "passed", "failed"])),
                ("Duration (s)", "所要時間（秒）", lambda: rng.randint(40, 1900)), ("Tests", "テスト数", lambda: rng.randint(120, 4800))]
    elif d == "HR":
        cols = [("Requisition", "求人番号", lambda: "REQ-%04d" % rng.randint(1, 9999)),
                ("Department", "部署", lambda: pick(["Sales", "Engineering", "Finance", "Marketing", "Legal"])),
                ("Position", "職種", lambda: pick(["Engineer", "Account Executive", "Analyst", "Designer", "Coordinator"])),
                ("Opened", "開始日", lambda: rand_date(ctx)), ("Applicants", "応募者数", lambda: rng.randint(3, 140)),
                ("Status", "状況", lambda: pick(["Open", "Interviewing", "Offer", "Closed"]))]
    elif d == "Finance":
        cols = [("Date", "日付", lambda: rand_date(ctx)),
                ("Team", "チーム", lambda: pick(["Sales", "Engineering", "Marketing", "HR", "Legal"])),
                ("Category", "区分", lambda: pick(["Travel", "Software", "Equipment", "Training", "Meals"])),
                ("Description", "内容", lambda: pick(["Client visit", "Annual license", "Laptop", "Workshop", "Team lunch"])),
                ("Amount (JPY)", "金額（円）", lambda: rng.randint(5, 2400) * 100)]
    elif d == "Legal":
        cols = [("Contract ID", "契約番号", lambda: "C-%04d-%03d" % (ctx.when.year, rng.randint(1, 999))),
                ("Counterparty", "取引先", lambda: pick(VENDORS + CUSTOMERS)[1 if ja else 0]),
                ("Type", "種別", lambda: pick(["MSA", "NDA", "SOW", "License"])),
                ("Start", "開始日", lambda: rand_date(ctx)), ("Term (months)", "期間（月）", lambda: pick([6, 12, 24, 36])),
                ("Status", "状況", lambda: pick(["Active", "Active", "Expired", "In review"]))]
    elif d == "Marketing":
        cols = [("Date", "日付", lambda: rand_date(ctx)), ("Campaign", "キャンペーン", lambda: pick(CAMPAIGNS)[1 if ja else 0]),
                ("Channel", "チャネル", lambda: pick(["Email", "Search", "Social", "Webinar", "Display"])),
                ("Impressions", "表示回数", lambda: rng.randint(800, 250000)), ("Clicks", "クリック数", lambda: rng.randint(10, 9000)),
                ("Cost (JPY)", "費用（円）", lambda: rng.randint(2, 480) * 1000)]
    else:
        cols = [("Item", "項目", lambda: pick(["Meeting room", "Projector", "Badge reader", "Printer", "Locker"])),
                ("Location", "場所", lambda: pick(["Tokyo HQ 3F", "Tokyo HQ 5F", "Osaka Office", "Nagoya Office"])),
                ("Owner", "担当", lambda: DEPT_TEAMS[pick(list(DEPT_TEAMS))][1 if ja else 0]),
                ("Checked", "確認日", lambda: rand_date(ctx)), ("Quantity", "数量", lambda: rng.randint(1, 30))]
    headers = [c[1] if ja else c[0] for c in cols]
    return headers, [[c[2]() for c in cols] for _ in range(rows)]


ROWS_BY_SIZE = {"small": (8, 25), "medium": (200, 900), "large": (3000, 6000), "xl": (22000, 24000)}

# ---------------------------------------------------------------------------
# Renderers: text formats
# ---------------------------------------------------------------------------


def render_txt(doc, ctx):
    out = [doc.title, "=" * min(len(doc.title) * (2 if not is_ascii(doc.title) else 1), 78),
           "Codelibs, Inc. - %s" % doc.team, doc.when.date().isoformat(), ""]
    for heading, paras in doc.paragraphs():
        out += [heading, "-" * min(len(heading) * (2 if not is_ascii(heading) else 1), 78), ""]
        for p in paras:
            out += textwrap.wrap(p, 88) if is_ascii(p) else [p]
            out.append("")
    if doc.table:
        out.append("\t".join(doc.table[0]))
        out += ["\t".join(r) for r in doc.table[1]]
        out.append("")
    return "\n".join(out).encode("utf-8")


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return lines


def render_md(doc, ctx):
    out = ["# " + doc.title, "", "_Codelibs, Inc. - %s - %s_" % (doc.team, doc.when.date().isoformat()), ""]
    for heading, paras in doc.paragraphs():
        out += ["## " + heading, ""]
        for k, p in enumerate(paras):
            out.append(("- " + p) if k % 2 == 1 else p)
            out.append("")
    if doc.table:
        out += md_table(*doc.table)
        out.append("")
    return "\n".join(out).encode("utf-8")


def render_html(doc, ctx):
    lang = {"en": "en", "ja": "ja", "mix": "ja"}[doc.lang]
    desc = doc.sections[0][1][0][0]
    parts = ['<!DOCTYPE html>', '<html lang="%s">' % lang, '<head>', '<meta charset="UTF-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>%s</title>" % xml_escape(doc.title),
             '<meta name="description" content="%s">' % xml_escape(desc[:160], {'"': "&quot;"}),
             "<style>body{font-family:sans-serif;max-width:46em;margin:2em auto;line-height:1.6}"
             "table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:.2em .6em}</style>",
             "</head>", "<body>", "<header><h1>%s</h1>" % xml_escape(doc.title),
             "<p>Codelibs, Inc. - %s - <time datetime=\"%s\">%s</time></p></header>" % (
                 xml_escape(doc.team), doc.when.date().isoformat(), doc.when.date().isoformat()), "<main>"]
    for heading, paras in doc.paragraphs():
        parts.append("<section><h2>%s</h2>" % xml_escape(heading))
        parts += ["<p>%s</p>" % xml_escape(p) for p in paras]
        parts.append("</section>")
    if doc.table:
        parts.append("<table><thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % xml_escape(h) for h in doc.table[0]))
        parts += ["<tr>%s</tr>" % "".join("<td>%s</td>" % xml_escape(c) for c in r) for r in doc.table[1]]
        parts.append("</tbody></table>")
    parts += ["</main>", "<footer><small>&copy; Codelibs, Inc.</small></footer>", "</body>", "</html>", ""]
    return "\n".join(parts).encode("utf-8")


def render_csv(headers, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    for row in rows:
        w.writerow([v.isoformat() if isinstance(v, dt.date) else v for v in row])
    return buf.getvalue().encode("utf-8")


def render_json(ctx, topic, headers, rows, title_slug):
    rng = ctx.rng
    if ctx.dept == "Engineering" and rng.random() < 0.6:
        svc = ctx.proj[2]
        data = {
            "service": svc, "version": "%d.%d.%d" % (rng.randint(1, 4), rng.randint(0, 12), rng.randint(0, 9)),
            "environment": rng.choice(["production", "staging"]), "owner": ctx.team[0],
            "description": ctx.proj[1] if ctx.lang == "ja" else ctx.proj[0] + " configuration",
            "endpoints": [{"path": p, "method": m, "timeout_ms": rng.choice([1000, 3000, 5000]), "auth": "token"}
                          for p, m in [("/v1/orders", "GET"), ("/v1/orders", "POST"), ("/v1/customers/{id}", "GET"),
                                       ("/v1/health", "GET"), ("/v1/reports/monthly", "GET")][:rng.randint(3, 5)]],
            "limits": {"requests_per_minute": rng.choice([120, 600, 1200]), "max_payload_kb": rng.choice([64, 256, 1024])},
            "updated": ctx.when.date().isoformat(),
        }
    else:
        keys = [h.lower().replace(" ", "_").replace("(", "").replace(")", "") if is_ascii(h) else h for h in headers]
        data = {"company": "Codelibs, Inc.", "dataset": title_slug, "generated": ctx.when.date().isoformat(),
                "records": [{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in zip(keys, row)} for row in rows]}
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_log(ctx, lines):
    rng = ctx.rng
    svc = ctx.proj[2]
    t = ctx.when.replace(hour=0, minute=0, second=0)
    out = []
    for _ in range(lines):
        t += dt.timedelta(seconds=rng.randint(1, 9))
        level = rng.choices(["INFO", "INFO", "INFO", "INFO", "WARN", "ERROR"], k=1)[0]
        path = rng.choice(["/v1/orders", "/v1/customers", "/v1/health", "/v1/reports/monthly"])
        status = 200 if level == "INFO" else rng.choice([429, 500, 503])
        out.append("%s %s [%s] request completed path=%s status=%d duration_ms=%d" % (
            t.strftime("%Y-%m-%d %H:%M:%S"), level, svc, path, status, rng.randint(3, 900)))
    return ("\n".join(out) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Renderers: OOXML (docx, xlsx, pptx)
# ---------------------------------------------------------------------------

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
OOXML_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def make_zip(parts):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, date_time=OOXML_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data if isinstance(data, bytes) else data.encode("utf-8"))
    return bio.getvalue()


def content_types(defaults_overrides):
    parts = [XML_DECL, '<Types xmlns="%s">' % NS_CT,
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
             '<Default Extension="xml" ContentType="application/xml"/>']
    parts += ['<Override PartName="%s" ContentType="%s"/>' % kv for kv in defaults_overrides]
    parts.append("</Types>")
    return "".join(parts)


def rels(items):
    return XML_DECL + '<Relationships xmlns="%s">' % NS_REL + "".join(
        '<Relationship Id="%s" Type="%s" Target="%s"/>' % item for item in items) + "</Relationships>"


def core_props(title, when, lang):
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (XML_DECL + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>%s</dc:title><dc:creator>Codelibs, Inc.</dc:creator>'
            '<dc:language>%s</dc:language><dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified></cp:coreProperties>' % (
                xml_escape(title), "ja-JP" if lang != "en" else "en-US", iso, iso))


def app_props(application):
    return (XML_DECL + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>%s</Application><Company>Codelibs, Inc.</Company></Properties>" % application)


COMMON_RELS = [("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
               ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "docProps/app.xml")]
COMMON_CT = [("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
             ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml")]

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def w_par(text, style=None):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return '<w:p>%s<w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (ppr, xml_escape(text))


DOCX_STYLES = (XML_DECL + '<w:styles xmlns:w="%s"><w:docDefaults><w:rPrDefault><w:rPr>'
               '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Yu Gothic" w:cs="Arial"/><w:sz w:val="21"/><w:szCs w:val="21"/>'
               '<w:lang w:val="en-US" w:eastAsia="ja-JP"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/>'
               '</w:pPr></w:pPrDefault></w:docDefaults>'
               '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
               '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
               '<w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>'
               '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
               '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>'
               '<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/>'
               '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
               '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
               '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/><w:tblPr><w:tblBorders>'
               '<w:top w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:left w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
               '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:right w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
               '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
               "</w:tblBorders></w:tblPr></w:style></w:styles>") % W_NS


def render_docx(doc, ctx):
    body = [w_par(doc.title, "Title"),
            w_par("Codelibs, Inc. - %s - %s" % (doc.team, doc.when.date().isoformat()))]
    for heading, paras in doc.paragraphs():
        body.append(w_par(heading, "Heading1"))
        body += [w_par(p) for p in paras]
    if doc.table:
        headers, rows = doc.table
        width = 9000 // len(headers)
        tbl = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>']
        tbl.append("".join('<w:gridCol w:w="%d"/>' % width for _ in headers) + "</w:tblGrid>")
        for r, row in enumerate([headers] + rows):
            tbl.append("<w:tr>")
            for cell in row:
                run = "<w:rPr><w:b/></w:rPr>" if r == 0 else ""
                tbl.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr><w:p><w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p></w:tc>' % (
                    width, run, xml_escape(cell)))
            tbl.append("</w:tr>")
        tbl.append("</w:tbl><w:p/>")
        body.append("".join(tbl))
    document = (XML_DECL + '<w:document xmlns:w="%s"><w:body>%s<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
                "</w:sectPr></w:body></w:document>") % (W_NS, "".join(body))
    return make_zip([
        ("[Content_Types].xml", content_types([
            ("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
            ("/word/styles.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml")] + COMMON_CT)),
        ("_rels/.rels", rels([("rId1", NS_DOCREL + "/officeDocument", "word/document.xml")] + COMMON_RELS)),
        ("word/_rels/document.xml.rels", rels([("rId1", NS_DOCREL + "/styles", "styles.xml")])),
        ("word/document.xml", document),
        ("word/styles.xml", DOCX_STYLES),
        ("docProps/core.xml", core_props(doc.title, doc.when, doc.lang)),
        ("docProps/app.xml", app_props("Microsoft Office Word")),
    ])


def col_name(i):
    name = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        name = chr(65 + r) + name
    return name


def excel_serial(d):
    return (d - dt.date(1899, 12, 30)).days


def sheet_xml(headers, rows, strings):
    """Worksheet XML; text goes to the shared string table, dates and numbers are typed cells."""
    def sidx(text):
        return strings.setdefault(text, len(strings))
    out = [XML_DECL, '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0">'
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>']
    out.append('<col min="1" max="%d" width="18" customWidth="1"/></cols><sheetData>' % len(headers))
    out.append('<row r="1">' + "".join('<c r="%s1" t="s" s="1"><v>%d</v></c>' % (col_name(i), sidx(h)) for i, h in enumerate(headers)) + "</row>")
    for r, row in enumerate(rows, start=2):
        cells = []
        for i, v in enumerate(row):
            ref = "%s%d" % (col_name(i), r)
            if isinstance(v, dt.date):
                cells.append('<c r="%s" s="2"><v>%d</v></c>' % (ref, excel_serial(v)))
            elif isinstance(v, bool) or not isinstance(v, (int, float)):
                cells.append('<c r="%s" t="s"><v>%d</v></c>' % (ref, sidx(str(v))))
            else:
                cells.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, 3 if isinstance(v, int) and abs(v) >= 1000 else 0, v))
        out.append('<row r="%d">%s</row>' % (r, "".join(cells)))
    out.append("</sheetData></worksheet>")
    return "".join(out)


XLSX_STYLES = (XML_DECL + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>'
               '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
               '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
               '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
               '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
               '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
               '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
               '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
               '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def render_xlsx(ctx, title, sheets):
    """sheets: [(sheet name, headers, rows), ...]"""
    strings = {}
    sheet_parts = [("xl/worksheets/sheet%d.xml" % (i + 1), sheet_xml(h, r, strings)) for i, (_, h, r) in enumerate(sheets)]
    sst = (XML_DECL + '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="%d" uniqueCount="%d">' % (
        len(strings), len(strings)) + "".join('<si><t xml:space="preserve">%s</t></si>' % xml_escape(s) for s in strings) + "</sst>")
    workbook = (XML_DECL + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="%s"><sheets>%s</sheets></workbook>' % (
        NS_DOCREL, "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (xml_escape(n, {'"': "&quot;"}), i + 1, i + 1)
                           for i, (n, _, _) in enumerate(sheets))))
    n = len(sheets)
    wb_rels = rels([("rId%d" % (i + 1), NS_DOCREL + "/worksheet", "worksheets/sheet%d.xml" % (i + 1)) for i in range(n)] + [
        ("rId%d" % (n + 1), NS_DOCREL + "/styles", "styles.xml"), ("rId%d" % (n + 2), NS_DOCREL + "/sharedStrings", "sharedStrings.xml")])
    overrides = [("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
                 ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
                 ("/xl/sharedStrings.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")]
    overrides += [("/xl/worksheets/sheet%d.xml" % (i + 1), "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
                  for i in range(n)]
    return make_zip([
        ("[Content_Types].xml", content_types(overrides + COMMON_CT)),
        ("_rels/.rels", rels([("rId1", NS_DOCREL + "/officeDocument", "xl/workbook.xml")] + COMMON_RELS)),
        ("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", wb_rels), ("xl/styles.xml", XLSX_STYLES),
        ("xl/sharedStrings.xml", sst)] + sheet_parts + [
        ("docProps/core.xml", core_props(title, ctx.when, ctx.lang)), ("docProps/app.xml", app_props("Microsoft Excel"))])


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
P_ROOT = 'xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (A_NS, NS_DOCREL, P_NS)
GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
       '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


def placeholder(sid, name, ph, geom=None, body=""):
    sp_pr = "<p:spPr>%s</p:spPr>" % (
        '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>' % geom
        if geom else "")
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr>'
            "%s<p:txBody><a:bodyPr/><a:lstStyle/>%s</p:txBody></p:sp>") % (sid, name, ph, sp_pr, body or "<a:p><a:endParaRPr lang=\"en-US\"/></a:p>")


def a_par(text, size=None):
    rpr = '<a:rPr lang="%s"%s/>' % ("ja-JP" if not is_ascii(text) else "en-US", ' sz="%d"' % size if size else "")
    return "<a:p><a:r>%s<a:t>%s</a:t></a:r></a:p>" % (rpr, xml_escape(text))


PPTX_THEME = (XML_DECL + '<a:theme xmlns:a="%s" name="Example Theme"><a:themeElements><a:clrScheme name="Example">'
              '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
              '<a:dk2><a:srgbClr val="1F3A5F"/></a:dk2><a:lt2><a:srgbClr val="EEF2F6"/></a:lt2>'
              '<a:accent1><a:srgbClr val="2E6DA4"/></a:accent1><a:accent2><a:srgbClr val="D9822B"/></a:accent2>'
              '<a:accent3><a:srgbClr val="5B9A4D"/></a:accent3><a:accent4><a:srgbClr val="8E5BA6"/></a:accent4>'
              '<a:accent5><a:srgbClr val="C0504D"/></a:accent5><a:accent6><a:srgbClr val="4BACC6"/></a:accent6>'
              '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
              '<a:fontScheme name="Example"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Yu Gothic"/><a:cs typeface="Arial"/></a:majorFont>'
              '<a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Yu Gothic"/><a:cs typeface="Arial"/></a:minorFont></a:fontScheme>'
              '<a:fmtScheme name="Example"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
              '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
              '<a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
              '<a:ln w="25400" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
              '<a:ln w="38100" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln></a:lnStyleLst>'
              '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
              '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
              '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>'
              "</a:themeElements></a:theme>") % A_NS

PPTX_MASTER = (XML_DECL + "<p:sldMaster %s><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg><p:spTree>%s%s%s</p:spTree></p:cSld>"
               '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
               'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
               '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
               '<p:txStyles><p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="3200" b="1"><a:solidFill><a:schemeClr val="tx2"/></a:solidFill>'
               '<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
               '<p:bodyStyle><a:lvl1pPr marL="342900" indent="-342900"><a:buChar char="&#8226;"/><a:defRPr sz="2000"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
               '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
               "<p:otherStyle><a:lvl1pPr><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:otherStyle></p:txStyles></p:sldMaster>") % (
    P_ROOT, GRP, placeholder(2, "Title Placeholder 1", 'type="title"', (609600, 365125, 10972800, 1000125)),
    placeholder(3, "Content Placeholder 2", 'idx="1"', (609600, 1600200, 10972800, 4525963)))

PPTX_LAYOUT = (XML_DECL + '<p:sldLayout %s type="obj" preserve="1"><p:cSld name="Title and Content"><p:spTree>%s%s%s</p:spTree></p:cSld>'
               "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>") % (
    P_ROOT, GRP, placeholder(2, "Title 1", 'type="title"'), placeholder(3, "Content Placeholder 2", 'idx="1"'))


def render_pptx(doc, ctx):
    titles = [doc.title]
    slides = [[a_par("Codelibs, Inc."), a_par("%s - %s" % (doc.team, doc.when.date().isoformat()))]]
    for heading, paras in doc.sections[:12]:
        titles.append(heading)
        slides.append([a_par(s) for p in paras for s in p][:5])
    if doc.table:
        slides.append([a_par(" | ".join(r)) for r in [doc.table[0]] + doc.table[1][:5]])
        titles.append("Data" if doc.lang == "en" else "データ")
    n = len(slides)
    parts = [
        ("[Content_Types].xml", content_types([
            ("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
            ("/ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
            ("/ppt/slideLayouts/slideLayout1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
            ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml")] + [
            ("/ppt/slides/slide%d.xml" % (i + 1), "application/vnd.openxmlformats-officedocument.presentationml.slide+xml") for i in range(n)]
            + COMMON_CT)),
        ("_rels/.rels", rels([("rId1", NS_DOCREL + "/officeDocument", "ppt/presentation.xml")] + COMMON_RELS)),
        ("ppt/presentation.xml", XML_DECL + "<p:presentation %s><p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst>"
         "<p:sldIdLst>%s</p:sldIdLst><p:sldSz cx=\"12192000\" cy=\"6858000\"/><p:notesSz cx=\"6858000\" cy=\"9144000\"/></p:presentation>" % (
             P_ROOT, "".join('<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, i + 3) for i in range(n)))),
        ("ppt/_rels/presentation.xml.rels", rels([("rId1", NS_DOCREL + "/slideMaster", "slideMasters/slideMaster1.xml"),
                                                  ("rId2", NS_DOCREL + "/theme", "theme/theme1.xml")] + [
            ("rId%d" % (i + 3), NS_DOCREL + "/slide", "slides/slide%d.xml" % (i + 1)) for i in range(n)])),
        ("ppt/slideMasters/slideMaster1.xml", PPTX_MASTER),
        ("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels([("rId1", NS_DOCREL + "/slideLayout", "../slideLayouts/slideLayout1.xml"),
                                                               ("rId2", NS_DOCREL + "/theme", "../theme/theme1.xml")])),
        ("ppt/slideLayouts/slideLayout1.xml", PPTX_LAYOUT),
        ("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels([("rId1", NS_DOCREL + "/slideMaster", "../slideMasters/slideMaster1.xml")])),
        ("ppt/theme/theme1.xml", PPTX_THEME),
    ]
    for i, (title, body) in enumerate(zip(titles, slides)):
        slide = (XML_DECL + "<p:sld %s><p:cSld><p:spTree>%s%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>") % (
            P_ROOT, GRP, placeholder(2, "Title 1", 'type="title"', body=a_par(title)),
            placeholder(3, "Content Placeholder 2", 'idx="1"', body="".join(body)))
        parts.append(("ppt/slides/slide%d.xml" % (i + 1), slide))
        parts.append(("ppt/slides/_rels/slide%d.xml.rels" % (i + 1), rels([("rId1", NS_DOCREL + "/slideLayout", "../slideLayouts/slideLayout1.xml")])))
    parts += [("docProps/core.xml", core_props(doc.title, doc.when, doc.lang)), ("docProps/app.xml", app_props("Microsoft Office PowerPoint"))]
    return make_zip(parts)


# ---------------------------------------------------------------------------
# Renderer: PDF (Helvetica for ASCII lines, a non-embedded Japanese CID font otherwise)
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H, MARGIN = 595, 842, 56


def text_width(text, size):
    return sum((0.52 if ord(c) < 128 else 1.0) * size for c in text)


def wrap_text(text, size, width):
    lines, cur, cur_w = [], "", 0.0
    tokens, buf = [], ""
    for c in text:
        if ord(c) < 128:
            buf += c
            if c == " ":
                tokens.append(buf)
                buf = ""
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(c)
    if buf:
        tokens.append(buf)
    for tok in tokens:
        w = text_width(tok, size)
        if cur and cur_w + w > width:
            lines.append(cur.rstrip())
            cur, cur_w = "", 0.0
        cur += tok
        cur_w += w
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


def pdf_literal(text):
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def pdf_hex(text):
    return "<" + text.encode("utf-16-be").hex().upper() + ">"


def pdf_text_string(text):
    return "<FEFF" + text.encode("utf-16-be").hex().upper() + ">"


def render_pdf(doc, ctx, image_side=0):
    rng = ctx.rng
    lines = [(doc.title, 17, True)]
    lines.append(("Codelibs, Inc. - %s - %s" % (doc.team, doc.when.date().isoformat()), 9, False))
    lines.append(("", 9, False))
    for heading, paras in doc.paragraphs():
        lines.append((heading, 13, True))
        for p in paras:
            lines += [(ln, 10.5, False) for ln in wrap_text(p, 10.5, PAGE_W - 2 * MARGIN)]
            lines.append(("", 6, False))
    if doc.table:
        for row in [doc.table[0]] + doc.table[1]:
            lines += [(ln, 9.5, row is doc.table[0]) for ln in wrap_text("  |  ".join(row), 9.5, PAGE_W - 2 * MARGIN)]
    pages, cur, y = [], [], PAGE_H - MARGIN - (150 if image_side else 0)
    for text, size, bold in lines:
        lead = size * 1.5
        if y - lead < MARGIN:
            pages.append(cur)
            cur, y = [], PAGE_H - MARGIN
        y -= lead
        cur.append((text, size, bold, y))
    pages.append(cur)

    objs = {}
    n_pages = len(pages)
    first_page_obj = 9
    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join("%d 0 R" % (first_page_obj + 2 * i + 1) for i in range(n_pages))
    objs[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n_pages)
    objs[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objs[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    objs[5] = ("<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiKakuGo-W5-UniJIS-UCS2-HW-H /Encoding /UniJIS-UCS2-HW-H "
               "/DescendantFonts [6 0 R] >>")
    objs[6] = ("<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiKakuGo-W5 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) "
               "/Supplement 2 >> /FontDescriptor 7 0 R /DW 1000 /W [231 632 500] >>")
    objs[7] = ("<< /Type /FontDescriptor /FontName /HeiseiKakuGo-W5 /Flags 4 /FontBBox [-92 -250 1010 922] /ItalicAngle 0 "
               "/Ascent 752 /Descent -271 /CapHeight 737 /StemV 114 >>")
    info = "<< /Title %s /Author %s /Producer (Codelibs, Inc. sample generator) /CreationDate (D:%sZ) /ModDate (D:%sZ) >>" % (
        pdf_text_string(doc.title), pdf_text_string("Codelibs, Inc. / " + doc.team), doc.when.strftime("%Y%m%d%H%M%S"),
        doc.when.strftime("%Y%m%d%H%M%S"))
    objs[8] = info
    streams = {}
    image_obj = first_page_obj + 2 * n_pages
    for i, page in enumerate(pages):
        # A colour bar and a Latin footer on every page: the thumbnail generator has no
        # Japanese font, so without them a Japanese page would render completely blank.
        ops = ["0.18 0.43 0.64 rg %d %d %d 8 re f 0 g" % (MARGIN, PAGE_H - 40, PAGE_W - 2 * MARGIN),
               "BT /F1 8 Tf 1 0 0 1 %d 30 Tm %s Tj ET" % (MARGIN, pdf_literal("Codelibs, Inc. - sample document - page %d of %d" % (i + 1, n_pages)))]
        if i == 0 and image_side:
            ops.append("q 140 0 0 140 %d %d cm /Im1 Do Q" % (PAGE_W - MARGIN - 140, PAGE_H - MARGIN - 140))
        for text, size, bold, y in page:
            if not text:
                continue
            x = MARGIN
            if is_ascii(text):
                ops.append("BT /%s %.1f Tf 1 0 0 1 %d %.1f Tm %s Tj ET" % ("F2" if bold else "F1", size, x, y, pdf_literal(text)))
            else:
                ops.append("BT /F3 %.1f Tf 1 0 0 1 %d %.1f Tm %s Tj ET" % (size, x, y, pdf_hex(text)))
        data = zlib.compress("\n".join(ops).encode("ascii"), 6)
        content_id, page_id = first_page_obj + 2 * i, first_page_obj + 2 * i + 1
        streams[content_id] = ("<< /Filter /FlateDecode /Length %d >>" % len(data), data)
        xobj = " /XObject << /Im1 %d 0 R >>" % image_obj if image_side else ""
        objs[page_id] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R "
                         "/F3 5 0 R >>%s >> >>" % (PAGE_W, PAGE_H, content_id, xobj))
    if image_side:
        s = image_side
        rows = bytearray()
        for yy in range(s):  # a gradient with noise, so the stream does not compress away
            noise = rand_bytes(rng, s * 3)
            rows += bytes((k * 255 // (3 * s) + (noise[k] >> 1) + yy) & 255 for k in range(3 * s))
        data = zlib.compress(bytes(rows), 6)
        streams[image_obj] = ("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                              "/Filter /FlateDecode /Length %d >>" % (s, s, len(data)), data)
    total = max(list(objs) + list(streams))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in range(1, total + 1):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num
        if num in streams:
            d, data = streams[num]
            out += d.encode("ascii") + b"\nstream\n" + data + b"\nendstream"
        else:
            out += objs[num].encode("ascii")
        out += b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (total + 1)
    for num in range(1, total + 1):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 8 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (total + 1, xref)
    return bytes(out)


# ---------------------------------------------------------------------------
# Renderer: PNG (charts drawn by a tiny rasterizer)
# ---------------------------------------------------------------------------

PALETTE = [(46, 109, 164), (217, 130, 43), (91, 154, 77), (142, 91, 166), (192, 80, 77), (75, 172, 198)]


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def itxt(key, text):
    return png_chunk(b"iTXt", key.encode("latin-1") + b"\0\0\0\0\0" + text.encode("utf-8"))


def render_png(ctx, title, description, w, h, noise):
    rng = ctx.rng
    bg = (246, 248, 251)
    rows = [bytearray(bytes(bg) * w) for _ in range(h)]

    def fill(x0, y0, x1, y1, color):
        x0, x1 = max(0, x0), min(w, x1)
        for y in range(max(0, y0), min(h, y1)):
            rows[y][x0 * 3:x1 * 3] = bytes(color) * (x1 - x0)
    pad = max(6, w // 16)
    fill(pad, h - pad, w - pad, h - pad + 2, (90, 98, 110))  # x axis
    fill(pad, pad, pad + 2, h - pad, (90, 98, 110))  # y axis
    for g in range(1, 4):  # grid lines
        fill(pad + 2, pad + g * (h - 2 * pad) // 4, w - pad, pad + g * (h - 2 * pad) // 4 + 1, (222, 226, 232))
    style = rng.choice(["bars", "bars", "stacked", "steps"])
    n = rng.randint(5, 9) if w >= 200 else 3
    slot = max(1, (w - 2 * pad - 4) // n)
    base_y = h - pad
    top_room = h - 2 * pad - 4
    color = rng.choice(PALETTE)
    prev = None
    for i in range(n):
        x0 = pad + 4 + i * slot + slot // 6
        bw = max(1, slot * 2 // 3)
        height = rng.randint(top_room // 5, top_room)
        if style == "bars":
            fill(x0, base_y - height, x0 + bw, base_y, color)
        elif style == "stacked":
            h1 = height * rng.randint(30, 70) // 100
            fill(x0, base_y - h1, x0 + bw, base_y, PALETTE[0])
            fill(x0, base_y - height, x0 + bw, base_y - h1, PALETTE[1])
        else:
            if prev is not None:
                fill(prev[0], min(prev[1], base_y - height), x0 + bw, min(prev[1], base_y - height) + 3, color)
            fill(x0, base_y - height, x0 + bw, base_y - height + 3, color)
            fill(x0, base_y - height, x0 + 3, base_y, color)
            prev = (x0, base_y - height)
    if noise:
        for y in range(h):
            r = rand_bytes(rng, w * 3)
            row = rows[y]
            for i in range(w * 3):
                v = row[i] + (r[i] * (2 * noise + 1) >> 8) - noise
                row[i] = 0 if v < 0 else 255 if v > 255 else v
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + itxt("Title", title)
            + itxt("Description", description) + png_chunk(b"IDAT", zlib.compress(raw, 6)) + png_chunk(b"IEND", b""))


# ---------------------------------------------------------------------------
# Plan: which files exist, where and when
# ---------------------------------------------------------------------------

QUARTERS = [(2023, 4)] + [(y, q) for y in (2024, 2025) for q in (1, 2, 3, 4)] + [(2026, q) for q in (1, 2, 3)]
STYLE_BY_LANG = {"en": ["snake", "space", "dated", "space"], "ja": ["ja", "ja_ver", "ja"], "mix": ["bilingual", "space", "ja"]}
KIND_EXT = {"txt": "txt", "md": "md", "html": "html", "csv": "csv", "json": "json", "pdf": "pdf", "docx": "docx", "xlsx": "xlsx",
            "pptx": "pptx", "png": "png", "log": "log"}


class Plan:
    def __init__(self, reference, seed):
        self.reference = reference
        self.seed = seed
        self.rng = random.Random("plan:%d" % seed)
        self.items = []
        self.used = set()

    def quarter_window(self, y, q):
        start = utc(y, 3 * q - 2, 1)
        end = utc(y + (q == 4), 1 if q == 4 else 3 * q + 1, 1) - dt.timedelta(days=1)
        return start, min(end, self.reference)

    def when_in(self, window):
        start, end = window or (self.reference - dt.timedelta(days=1096), self.reference)
        span = max(0, int((end - start).total_seconds() // 86400))
        day = start + dt.timedelta(days=self.rng.randint(0, span))
        return day.replace(hour=self.rng.randint(0, 9), minute=self.rng.randint(0, 59), second=0)

    def name_for(self, topic, lang, when, ext, rel_dir):
        """Pick a file name in the style of the language and make it unique within the folder."""
        en, ja = topic
        style = self.rng.choice(STYLE_BY_LANG[lang])
        d, ym = when.date().isoformat(), when.strftime("%Y-%m")
        if style == "snake":
            base = "%s_%s" % (en.lower().replace(" ", "_").replace("-", "_"), ym)
        elif style == "dated":
            base = "%s_%s" % (d, en.lower().replace(" ", "-"))
        elif style == "ja":
            base = "%s_%d年%d月" % (ja, when.year, when.month)
        elif style == "ja_ver":
            base = "%s %d年度版" % (ja, when.year if when.month >= 4 else when.year - 1)
        elif style == "bilingual":
            base = "%s（%s）%s" % (en, ja, ym)
        else:
            base = "%s %s" % (en, ym)
        name, k = "%s.%s" % (base, ext), 2
        while rel_dir + (name,) in self.used:
            name = "%s (%d).%s" % (base, k, ext)
            k += 1
        return name

    def add(self, path, dept, count, kinds, window=None, topics=None, size=None, lang=None, **ctx_args):
        topics = topics if topics is not None else list(range(len(TOPICS[dept])))
        for i in range(count):
            kind = kinds[i % len(kinds)]
            topic = TOPICS[dept][topics[(i + self.rng.randrange(len(topics))) % len(topics)]]
            flang = lang or self.rng.choices(["en", "ja", "mix"], [45, 40, 15])[0]
            when = self.when_in(window)
            ext = KIND_EXT[kind]
            rel_dir = tuple(path.split("/"))
            key = rel_dir + (self.name_for(topic, flang, when, ext, rel_dir),)
            self.used.add(key)
            fsize = size or self.rng.choices(["small", "medium", "large", "xl"], [50, 32, 14, 4])[0]
            self.items.append(dict(path=key, dept=dept, kind=kind, topic=topic, lang=flang, when=when, size=fsize, ctx=ctx_args))

    def add_named(self, path, dept, names, window=None, lang="en", size="small", **ctx_args):
        for entry in names:
            filename, topic_idx = entry[:2]
            kind = entry[2] if len(entry) > 2 else filename.rsplit(".", 1)[1]
            key = tuple(path.split("/")) + (filename,)
            self.used.add(key)
            self.items.append(dict(path=key, dept=dept, kind=kind, topic=TOPICS[dept][topic_idx], lang=lang,
                                   when=self.when_in(window), size=size, ctx=ctx_args))


def build_plan(reference, seed):
    p = Plan(reference, seed)
    ref = reference
    today = (ref, ref)
    last_week = (ref - dt.timedelta(days=6), ref)
    last_month = (ref - dt.timedelta(days=28), ref)
    recent_year = (ref - dt.timedelta(days=330), ref - dt.timedelta(days=40))
    recent = [q for q in QUARTERS if q[0] >= 2025]

    # --- Sales
    for y, q in QUARTERS:
        p.add("Sales/%d/Q%d/Reports" % (y, q), "Sales", 1, ["xlsx", "pdf", "docx"], p.quarter_window(y, q), topics=[0, 2])
    for y, q in recent[-4:]:
        for region in REGIONS:
            p.add("Sales/%d/Q%d/Regional Reports/%s" % (y, q, region[0]), "Sales", 1, ["xlsx", "docx", "pdf"], p.quarter_window(y, q),
                  topics=[0], region=region)
    for customer in CUSTOMERS:
        folder = customer[1] if customer[0].startswith(("Aoba", "Kawasemi")) else customer[0]
        p.add("Sales/Customers/%s" % folder, "Sales", 3, ["md", "txt", "pptx", "pdf", "docx"], topics=[1, 3, 4], customer=customer)
    p.add("Sales/Customers/%s/Contracts/2025" % CUSTOMERS[0][0], "Sales", 2, ["pdf", "docx"], p.quarter_window(2025, 2), topics=[3], customer=CUSTOMERS[0])
    p.add("Sales/Pipeline", "Sales", 3, ["csv", "json", "xlsx"], last_month, topics=[2])
    p.add("Sales/Pipeline", "Sales", 1, ["md"], today, topics=[2], lang="en", size="small")
    p.add("Sales/Pipeline/Archive", "Sales", 1, ["csv"], recent_year, topics=[2], size="xl")
    p.add("Sales/顧客対応/FAQ", "Sales", 3, ["md", "txt", "html"], topics=[5, 4], lang="ja")

    # --- Engineering
    for proj in PROJECTS:
        base = "Engineering/" + proj[0]
        p.add(base + "/design", "Engineering", 4, ["md", "pdf", "pptx", "docx"], topics=[0, 6, 5], proj=proj)
        p.add(base + "/docs/api", "Engineering", 3, ["html", "json", "md"], topics=[4], proj=proj, lang="en")
        p.add(base + "/docs/architecture/diagrams", "Engineering", 2, ["png"], topics=[6], proj=proj)
        for y, q in recent[-3:-1]:
            p.add(base + "/releases/%d/Q%d" % (y, q), "Engineering", 2, ["txt", "json", "md"], p.quarter_window(y, q), topics=[1], proj=proj)
        p.add(base + "/runbooks", "Engineering", 2, ["md", "pdf"], topics=[2], proj=proj)
    p.add("Engineering/Project Maple/設計書", "Engineering", 3, ["docx", "pdf", "md"], topics=[0, 6], lang="ja", proj=PROJECTS[0])
    p.add("Engineering/Project Maple/releases/2025/hotfix 2025-05/artifacts", "Engineering", 3, ["json", "txt", "png"],
          p.quarter_window(2025, 2), topics=[1], proj=PROJECTS[0], lang="en")
    p.add_named("Engineering/Project Maple/logs/2026-09", "Engineering", [("maple-gateway-application-2026-09-24.log", 1, "log")],
                last_week, proj=PROJECTS[0], size="xl")
    for y in (2024, 2025, 2026):
        p.add("Engineering/Incident Reports/%d" % y, "Engineering", 3, ["md", "pdf", "txt"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[3])

    # --- HR
    p.add("HR/Policies", "HR", 8, ["pdf", "docx", "md", "txt"], topics=[1, 5, 4])
    for y in (2024, 2025, 2026):
        p.add("HR/Recruiting/%d" % y, "HR", 2, ["xlsx", "csv", "pdf"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[3])
    p.add("HR/Onboarding", "HR", 6, ["md", "pptx", "html", "pdf", "txt", "docx"], topics=[0])
    for y, q in recent:
        p.add("HR/Training/%d/Q%d" % (y, q), "HR", 2 if q % 2 else 1, ["pptx", "pdf"], p.quarter_window(y, q), topics=[2])
    p.add("HR/Benefits", "HR", 2, ["pdf", "html"], topics=[5])

    # --- Finance
    for y, q in QUARTERS:
        p.add("Finance/%d/Q%d/Budgets" % (y, q), "Finance", 1, ["xlsx"], p.quarter_window(y, q), topics=[0])
    for y, q in recent[-4:]:
        for team in ("Sales", "Engineering", "Marketing"):
            p.add("Finance/%d/Q%d/Expense Reports/%s" % (y, q, team), "Finance", 1, ["csv", "xlsx"], p.quarter_window(y, q), topics=[1])
    for y in (2024, 2025):
        p.add("Finance/Audit/%d" % y, "Finance", 2, ["pdf", "docx"], (utc(y, 1, 1), utc(y, 12, 31)), topics=[3])
    p.add("Finance/Forecast", "Finance", 3, ["xlsx", "pdf", "pptx"], recent_year, topics=[2, 4])
    p.add("Finance/2026/Q3/Budgets", "Finance", 1, ["xlsx"], last_week, topics=[0], size="large")

    # --- Legal
    for y in (2024, 2025, 2026):
        for vendor in VENDORS[:2]:
            p.add("Legal/Contracts/%d/%s" % (y, vendor[0]), "Legal", 2, ["pdf", "docx"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)),
                  topics=[0, 4], vendor=vendor)
    p.add("Legal/Policies", "Legal", 5, ["pdf", "md", "docx"], topics=[2, 3])
    p.add("Legal/NDA", "Legal", 5, ["txt", "pdf", "docx", "txt"], topics=[1])
    p.add("Legal/Compliance", "Legal", 4, ["xlsx", "md", "pdf"], recent_year, topics=[3])

    # --- Marketing
    for campaign in CAMPAIGNS:
        folder = campaign[1] + "キャンペーン" if campaign[0].startswith("Spring") else campaign[0]
        p.add("Marketing/Campaigns/2025 %s/Materials" % folder, "Marketing", 5, ["pptx", "png", "html", "md", "docx"],
              (utc(2025, 1, 1), utc(2025, 12, 31)), topics=[0, 3], campaign=campaign)
    p.add("Marketing/Brand Assets/Logos", "Marketing", 6, ["png"], topics=[1], size="small")
    p.add("Marketing/Brand Assets/Guidelines", "Marketing", 2, ["pdf", "md"], topics=[1])
    p.add("Marketing/Brand Assets/Banners", "Marketing", 4, ["png"], topics=[0], size="large")
    p.add("Marketing/Brand Assets/Banners/Archive", "Marketing", 1, ["png"], recent_year, topics=[0], size="xl")
    for y in (2024, 2025, 2026):
        p.add("Marketing/Web Analytics/%d" % y, "Marketing", 2, ["csv", "json"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[2])
        p.add("Marketing/Press Releases/%d" % y, "Marketing", 2, ["html", "pdf", "md", "docx"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[3])
    p.add("Marketing/Web Analytics/2026", "Marketing", 1, ["json"], last_month, topics=[2], size="xl")
    p.add("Marketing/Content Calendar", "Marketing", 2, ["xlsx", "md"], last_month, topics=[4])

    # --- Shared
    for y in (2025, 2026):
        p.add("Shared/Announcements/%d" % y, "Shared", 3, ["html", "md", "txt"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[2])
    p.add("Shared/Announcements/2026", "Shared", 2, ["html", "txt"], last_week, topics=[2])
    p.add("Shared/Announcements/2026", "Shared", 2, ["html", "txt"], today, topics=[2], lang="en", size="small")
    p.add("Shared/Templates", "Shared", 6, ["docx", "xlsx", "pptx"], topics=[3])
    long_dir = ("Shared/Handbook/Employee Handbook 2025 (Revised Edition) - Chapter 3 - Remote Work, Business Travel, and Expense "
                "Policies for All Regional Offices/Appendix B - Frequently Asked Questions and Answers about Reimbursement and "
                "Approval Workflows")
    p.add(long_dir, "Shared", 3, ["pdf", "html", "md"], topics=[0, 4], lang="en", size="medium")
    p.add_named(long_dir, "Shared", [("Expense_Reimbursement_Approval_Workflow_Flowchart_and_Escalation_Rules_for_Regional_"
                                       "Offices_v3_FINAL_reviewed_by_Finance_and_Legal.pdf", 0)], size="medium")
    for y in (2024, 2025, 2026):
        p.add("Shared/Meeting Notes/%d" % y, "Shared", 4, ["md", "txt"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[1])
    p.add_named("Shared/Misc", "Shared", [("C# Coding Guidelines.md", 4), ("Growth plan 15% target.txt", 1),
                                           ("Q&A session (draft).md", 4), ("Cafeteria menu + events.html", 2),
                                           ("R&D budget 2025.xlsx", 3), ("Lunch & Learn, schedule.txt", 2)])
    # --- General Affairs (Japanese folder names)
    p.add("総務部/規程集/就業規則/改定履歴/2025年度", "GA", 3, ["pdf", "docx"], p.quarter_window(2025, 2), topics=[0], lang="ja")
    p.add("総務部/規程集", "GA", 3, ["pdf", "docx", "md"], topics=[0], lang="ja")
    for y in (2024, 2025, 2026):
        p.add("総務部/議事録/%d年" % y, "GA", 4, ["txt", "md", "docx", "txt"], (utc(y, 1, 1), min(utc(y, 12, 31), ref)), topics=[1], lang="ja")
    p.add("総務部/備品管理", "GA", 2, ["xlsx", "csv"], topics=[2], lang="ja")
    p.add("総務部/社内イベント/2026", "GA", 3, ["html", "png", "pptx"], (utc(2026, 1, 1), ref), topics=[3], lang="ja")
    p.add("総務部/社内イベント/2026", "GA", 1, ["txt"], last_week, topics=[3], lang="ja")
    return p.items


# ---------------------------------------------------------------------------
# Rendering and writing
# ---------------------------------------------------------------------------


def render_item(item, seed):
    rel = "/".join(item["path"])
    rng = random.Random("file:%d:%s" % (seed, rel))
    when, kind, size, lang = item["when"], item["kind"], item["size"], item["lang"]
    ctx = Ctx(rng, item["dept"], lang, when, **item["ctx"])
    topic = item["topic"]
    if kind == "png":
        dims = {"small": (160, 100, 0), "medium": (480, 300, 0), "large": (720, 450, 14), "xl": (800, 600, 22)}[size]
        title = "%s - %s" % topic
        return render_png(ctx, title, "%s (%s)" % (topic[0], when.date().isoformat()), *dims)
    if kind in ("csv", "json", "xlsx"):
        lo, hi = ROWS_BY_SIZE[size]
        rows = rng.randint(lo, hi)
        headers, data = dataset(ctx, rows, "ja" if lang == "ja" else "en")
        if kind == "csv":
            return render_csv(headers, data)
        if kind == "json":  # JSON is far more verbose per row than CSV
            return render_json(ctx, topic, headers, data[:max(5, len(data) // 4)], topic[0])
        extra = dataset(ctx, 6, "ja" if lang == "ja" else "en") if size != "small" else None
        sheets = [(topic[1] if lang == "ja" else topic[0], headers, data)]
        if extra:
            sheets.append(("Summary" if lang != "ja" else "サマリー", extra[0], extra[1]))
        return render_xlsx(ctx, "%s - %s" % topic, sheets)
    if kind == "log":
        return render_log(ctx, {"small": 40, "medium": 600, "large": 4000, "xl": 16000}[size])
    doc = build_doc(ctx, topic, size)
    if kind == "txt":
        return render_txt(doc, ctx)
    if kind == "md":
        return render_md(doc, ctx)
    if kind == "html":
        return render_html(doc, ctx)
    if kind == "docx":
        return render_docx(doc, ctx)
    if kind == "pptx":
        return render_pptx(doc, ctx)
    if kind == "pdf":
        return render_pdf(doc, ctx, image_side={"large": 300, "xl": 640}.get(size, 0))
    raise ValueError(kind)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/files", help="output directory (default: data/files)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE,
                    help="newest modification time as YYYY-MM-DD, or 'today' (default: %(default)s)")
    args = ap.parse_args()

    if args.reference_date == "today":
        t = dt.datetime.now(dt.timezone.utc)
        reference = utc(t.year, t.month, t.day, 12)
    else:
        y, m, d = (int(x) for x in args.reference_date.split("-"))
        reference = utc(y, m, d, 12)

    items = build_plan(reference, args.seed)
    out = os.path.abspath(args.out)
    dirs = set()
    total = 0
    for item in items:
        target = os.path.join(out, *item["path"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = render_item(item, args.seed)
        with open(target, "wb") as f:
            f.write(data)
        os.chmod(target, 0o644)
        stamp = epoch(item["when"])
        os.utime(target, (stamp, stamp))
        total += len(data)
        for depth in range(1, len(item["path"])):
            dirs.add(item["path"][:depth])
    for d in sorted(dirs, key=len, reverse=True):
        os.chmod(os.path.join(out, *d), 0o755)
        newest = max(epoch(i["when"]) for i in items if i["path"][:len(d)] == d)
        os.utime(os.path.join(out, *d), (newest, newest))
    os.chmod(out, 0o755)
    kinds = {}
    for item in items:
        kinds[KIND_EXT[item["kind"]]] = kinds.get(KIND_EXT[item["kind"]], 0) + 1
    print("Generated %d files in %d directories (%.1f MB) under %s" % (len(items), len(dirs) + 1, total / 1e6, out))
    print("By type: " + ", ".join("%s=%d" % kv for kv in sorted(kinds.items())))


if __name__ == "__main__":
    sys.exit(main())
