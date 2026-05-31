#!/usr/bin/env python3
"""
邮件发送脚本
读取汇总报告，通过QQ邮箱SMTP发送
"""
import os
import sys
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

BASE_DIR = "/Users/apple/Documents/分析报告/每周复盘重点关注"
SUMMARY_DIR = os.path.join(BASE_DIR, "_summary")

# 邮箱配置
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SMTP_USER = "broccoli_ovo@qq.com"
SMTP_PASS = "xtqhbfdfhmnijbai"
RECIPIENT = "broccoli_ovo@qq.com"


def find_latest_summary():
    """找到最新的汇总报告"""
    if not os.path.exists(SUMMARY_DIR):
        return None
    files = [f for f in os.listdir(SUMMARY_DIR) if f.endswith('_汇总报告.md')]
    if not files:
        return None
    files.sort(reverse=True)
    return os.path.join(SUMMARY_DIR, files[0])


def parse_summary_for_subject(filepath):
    """从汇总报告中提取信息用于邮件主题"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return None, 0, 0, 0
    date_match = re.search(r'投资组合周报汇总[—-]\s*(\d{4}-\d{2}-\d{2})', content)
    date_str = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
    normal = len(re.findall(r'🟢\s*正常', content))
    warning = len(re.findall(r'🟡\s*关注', content))
    alert = len(re.findall(r'🔴\s*告警', content))
    return date_str, normal, warning, alert


def send_email(summary_path):
    """发送邮件"""
    date_str, normal, warning, alert = parse_summary_for_subject(summary_path)
    with open(summary_path, 'r', encoding='utf-8') as f:
        report_content = f.read()
    subject = f"[投资组合周报] {date_str} | 🟢{normal} 🟡{warning} 🔴{alert}"
    body = f"""投资组合周报汇总 - {date_str}

========================================

{report_content}

========================================
本邮件由投资组合周报系统自动发送
"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    with open(summary_path, 'rb') as f:
        attachment = MIMEApplication(f.read())
        attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(summary_path))
        msg.attach(attachment)
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, RECIPIENT, msg.as_string())
        server.quit()
        print(f"邮件发送成功: {subject}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False


def main():
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
        summary_path = os.path.join(SUMMARY_DIR, f"{date_str}_汇总报告.md")
        if not os.path.exists(summary_path):
            print(f"错误: 找不到汇总报告 {summary_path}")
            sys.exit(1)
    else:
        summary_path = find_latest_summary()
        if not summary_path:
            print("错误: 找不到汇总报告")
            sys.exit(1)
    print(f"准备发送: {summary_path}")
    success = send_email(summary_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
