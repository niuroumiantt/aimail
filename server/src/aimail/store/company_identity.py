"""Shared identity normalization contract; PSL snapshot only, never network lookup."""

import re
from urllib.parse import urlsplit

import tldextract

PUBLIC_MAIL = set(
    "gmail.com googlemail.com outlook.com hotmail.com live.com msn.com yahoo.com "
    "yahoo.co.uk yahoo.com.sg yahoo.com.cn ymail.com rocketmail.com icloud.com me.com "
    "mac.com aol.com proton.me protonmail.com pm.me qq.com foxmail.com "
    "163.com 126.com yeah.net 188.com sina.com sina.cn sohu.com "
    "aliyun.com mail.com gmx.com gmx.de web.de tutanota.com fastmail.com "
    "zoho.com rambler.ru yandex.ru yandex.com mail.ru bk.ru inbox.ru "
    "list.ru naver.com daum.net hanmail.net 139.com 189.cn 21cn.com "
    "tom.com 263.net 2980.com ".split()
)
PSL = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def domain(value):
    value = value.strip().casefold()
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[1]
    parsed = urlsplit(value if "://" in value else "https://" + value)
    host = (parsed.hostname or "").rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    if not host or "." not in host or host.endswith(".invalid") or host in PUBLIC_MAIL:
        return ""
    part = PSL(host)
    result = part.top_domain_under_public_suffix or host.removeprefix("www.")
    return "" if result in PUBLIC_MAIL else result


def name(value):
    value = value.casefold().strip()
    value = re.sub(r"[\W_]+", " ", value)
    suffix = (
        r"\s+(?:co|company|ltd|limited|inc|incorporated|corp|corporation|"
        r"llc|plc|pte|gmbh|sarl|bv|ag|sa)$"
    )
    previous = None
    while previous != value:
        previous, value = value, re.sub(suffix, "", value).strip()
    value = re.sub(r"(?:有限责任公司|股份有限公司|有限公司)$", "", value)
    return re.sub(r"\s+", "", value)


def keys(fields):
    email = fields.get("email", "").strip().casefold()
    domains = {domain(fields.get("website", "")), domain(email)} - {""}
    return domains, email if domain(email) else ""


def matches(items, fields):
    domains, email = keys(fields)
    needle = name(fields.get("company", ""))
    result = []
    for item in items:
        reasons = []
        if email and email in item["emails"]:
            reasons.append("企业邮箱相同")
        if domains.intersection(item["domains"]):
            reasons.append("企业域名相同")
        strong = bool(reasons)
        if needle and any(name(alias) == needle for alias in item["names"]):
            reasons.append("公司名称相似，需核实")
        if reasons:
            result.append(
                {
                    "company_id": item["company_id"],
                    "company": item["company"],
                    "reasons": reasons,
                    "strong": strong,
                }
            )
    return result
