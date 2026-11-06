"""基于 team-task.py 的修正版：抓取岗位列表、读取详情、另存为 CSV。

运行方式：在本目录执行 .venv/bin/python team_task_fixed.py
每次运行生成新的 CSV，不覆盖原代码及已有数据。
"""

import csv
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# 沿用原代码的存档地址和招聘类型；不代表这些存档当前一定可访问。
LIST_URL = (
    "https://web.archive.org/web/20260515165600/"
    "https://zp.z2hospital.com/department/detailInfomore.action"
)
RECRUITMENT_TYPE = "507"
REQUEST_TIMEOUT = 10
REQUEST_INTERVAL = 1
OUTPUT_DIR = Path(__file__).resolve().parent
MISSING_VALUE = "none"


def get_page(url, session=None):
    """获取网页；请求失败时交给调用方处理，不将错误当成空页面。"""
    client = session if session is not None else requests
    response = client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_job_list(html, base_url):
    """沿用原代码，从 onclick 的第一段引号内容提取岗位编号。"""
    soup = BeautifulSoup(html, "html.parser")
    job_list = []

    for index, job in enumerate(soup.find_all("li", class_="zp_li"), start=1):
        title_node = job.find("div", class_="left_name")
        title = title_node.get_text(strip=True) if title_node else ""
        if not title:
            print(f"跳过第 {index} 个岗位：缺少岗位名称。")
            continue

        onclick = job.get("onclick", "")
        # 同时支持 openDetail('uuid') 和 openDetail("uuid")。
        match = re.search(r"(['\"])([^'\"]+)\1", onclick)
        if not match or not match.group(2).strip():
            print(f"跳过岗位「{title}」：无法从 onclick 提取岗位编号。")
            continue

        query = urlencode({"uuid": match.group(2).strip(), "zplx": RECRUITMENT_TYPE})
        # 替换列表页文件名，保留存档地址中嵌套的 https:// 和存档时间。
        detail_url = f"{base_url.rsplit('/', 1)[0]}/detailInfo.action?{query}"
        job_list.append({
            "title": title,
            "detail_url": detail_url,
            "education": MISSING_VALUE,
            "major": MISSING_VALUE,
        })

    return job_list


def parse_job_detail(html):
    """提取学历和专业；字段缺失时保留 none，不使用未赋值变量。"""
    soup = BeautifulSoup(html, "html.parser")
    detail_data = {"education": MISSING_VALUE, "major": MISSING_VALUE}
    field_keys = {"学历学位": "education", "专业": "major"}
    recognized_fields = 0

    for field in soup.find_all("div", class_="tr_name"):
        # 兼容“学历学位：”、换行和字段名中的空格。
        field_name = re.sub(r"\s+", "", field.get_text()).rstrip(":：")
        key = field_keys.get(field_name)
        if key is None:
            continue
        recognized_fields += 1

        value_node = field.find_next_sibling("div")
        # 下一项若已经是字段名，不能把它误当成当前字段的值。
        if value_node is None or "tr_name" in value_node.get("class", []):
            continue
        value = value_node.get_text(strip=True)
        if value:
            detail_data[key] = value

    if recognized_fields == 0:
        raise ValueError("页面中未找到学历或专业字段，请检查是否为正常详情页")
    return detail_data


def save_jobs(job_list, output_dir=None):
    """另存为带时间的 UTF-8 BOM CSV；空列表不写文件，已有文件不覆盖。"""
    if not job_list:
        raise ValueError("岗位列表为空，不生成 CSV")

    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = directory / f"招聘数据_修正版_{timestamp}.csv"

    # x 模式仅创建新文件，即使同名文件已经存在也不会覆盖。
    with output_path.open("x", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["岗位名", "学历", "专业", "链接"])
        for job in job_list:
            writer.writerow([
                job["title"],
                job.get("education", MISSING_VALUE),
                job.get("major", MISSING_VALUE),
                job["detail_url"],
            ])
    return output_path


def describe_request_error(error):
    """把常见请求异常转换为清楚的提示。"""
    if isinstance(error, requests.exceptions.HTTPError):
        status = error.response.status_code if error.response is not None else "未知"
        return f"HTTP {status}，网页请求失败"
    if isinstance(error, requests.exceptions.SSLError):
        return "SSL 连接失败"
    if isinstance(error, requests.exceptions.Timeout):
        return "请求超时"
    return f"网络请求失败：{error}"


def main():
    failed_count = 0
    complete_count = 0

    with requests.Session() as session:
        print("开始读取岗位列表……")
        try:
            html = get_page(LIST_URL, session)
        except requests.exceptions.RequestException as error:
            print(f"列表读取失败：{describe_request_error(error)}。未生成 CSV。")
            return 1

        job_list = parse_job_list(html, LIST_URL)
        if not job_list:
            print("未提取到有效岗位，请检查网页内容或选择器。未生成 CSV。")
            return 1
        print(f"提取到 {len(job_list)} 个岗位。")

        for index, job_data in enumerate(job_list, start=1):
            time.sleep(REQUEST_INTERVAL)
            print(f"[{index}/{len(job_list)}] {job_data['title']}")
            try:
                detail_html = get_page(job_data["detail_url"], session)
                job_data.update(parse_job_detail(detail_html))
            except requests.exceptions.RequestException as error:
                failed_count += 1
                print(f"  {describe_request_error(error)}；保留该岗位，详情填 none。")
            except ValueError as error:
                failed_count += 1
                print(f"  {error}；保留该岗位，详情填 none。")
            else:
                if all(job_data[key] != MISSING_VALUE for key in ("education", "major")):
                    complete_count += 1
                else:
                    print("  详情字段不完整，缺失内容填 none。")
                print(f"  学历：{job_data['education']}；专业：{job_data['major']}")

    try:
        output_path = save_jobs(job_list)
    except (OSError, ValueError) as error:
        print(f"CSV 保存失败：{error}")
        return 1

    incomplete_count = len(job_list) - complete_count - failed_count
    print(
        f"已保存 {len(job_list)} 个岗位：详情完整 {complete_count} 个，"
        f"字段不完整 {incomplete_count} 个，详情读取失败 {failed_count} 个。"
    )
    print(f"输出文件：{output_path}")
    return 0


# 只有直接运行本文件才开始抓取，导入函数不会联网或写文件。
if __name__ == "__main__":
    raise SystemExit(main())
