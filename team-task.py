from bs4 import BeautifulSoup                         #从库”bs4“里调用工具”BeautifulSoup“
import requests                                       #调用库
from urllib.parse import urljoin                      #依旧从urllib.parse 里调用 urljoin
import time                                           #导入库
import csv                                            #导入库




def get_page(url):                                    #定义函数，接收“url”
  response = requests.get(url, timeout=10)            #定义变量“response”，赋值为接收到的url,超时时间为10s 
  print(response.status_code)                         #打印网站返回的代码
  response.raise_for_status()                         #如果检测到返回的是错误码就终止程序
  response.encoding = response.apparent_encoding      #检测编码格式，强制规定正文编码（防乱码）

  #print(response.text[:500])                         #打印网站HTML的前500个字符(弃用)
  return response.text                                #返回HTML内容给程序





def parse_job_list(html, base_url):                   #定义函数，接收网页HTML和网站基础地址
  soup = BeautifulSoup(html, "html.parser")           #将返回的html按标准方法解析，赋值于变量

  job_card = "zp_li"#input()                          #预留input
  jobs = soup.find_all("li", class_=job_card)         #在返回的html查找所有class为job_card的<div>
  print(len(jobs))                                    #调试，检测长度

  job_list = []                                       #新建一个空列表

  for job in jobs:                                    #依次从jobs中取出一个岗位，并赋值给job
    title = job.find("div", class_="left_name")       #把找到的职业名称赋值给title(job-title目前是占位符，根据网页结构灵活改动)
    #print(title.text)                                 #输出名称（以纯文本形式） 

    onclick = job.get("onclick")                      #找出onclick属性，赋值
    job_id = onclick.split("'")[1]                    #切开字符串，留下uuid
    detail_url = f"https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfo.action?uuid={job_id}&zplx=507"#组合成完整的链接
    #print(onclick)
    #print(detail_url)
    job_data = {                                      #创建字典
      "title": title.text.strip(),
      "detail_url": detail_url
    }
    job_list.append(job_data)                         #循环把岗位放到列表
  return job_list                                     #输出




def parse_job_detail(html):                              #定义函数，接收岗位详情页HTML
    soup = BeautifulSoup(html, "html.parser")            #HTML按标准方式解析，赋值给soup
    fields = soup.find_all("div", class_="tr_name")      #找到所有class为tr_name的标签
    for field in fields:                                 #依次从fields中取出一个字段
        field_name = field.get_text(strip=True)           #提取当前字段名的纯文字，并去掉前后空格
        if field_name == "学历学位":                         #判断当前字段是否为“学历学位”
            education = field.find_next_sibling("div")      #找到当前字段后面同级的下一个div
            education_text = education.get_text(strip=True) #提取学历内容的纯文字，去掉空格
            #print(education_text)                         #测试
        if field_name == "专业":                          #判断专业
           major = field.find_next_sibling("div")#找到当前字段后面同级的下一个div
           major_text = major.get_text(strip=True)#提取学历内容的纯文字，去掉空格
           #print(major_text)

    detail_data = {                                      #创建岗位详情字典
        "education": education_text,                      #把学历信息加入字典
        "major": major_text,                            #把专业信息加入字典
    }
    return detail_data                                   #输出字典

      

#按标签解析，弃用
#def parse_job_detail(html):                           #定义新函数，获取网站职位信息详情
  #soup = BeautifulSoup(html, "html.parser")
  #education = soup.find("p", class_="education")      #找到带学历标签的（假设是education），保存到变量
  #education_text = education.text.strip()             #只保留文字

  #major = soup.find("p", class_="major")              #找到带专业标签的（假设是major），保存到变量
  #major_text = major.text.strip()                     #只保留文字

  #experience = soup.find("p", class_="experience")    #找到带工作经验标签的（假设是exp），保存到变量
  #experience_text = experience.text.strip()           #只保留文字

  #detail_data = {         
  #  "education": education_text,                      #在字典里加入edu
  #  "major": major_text,                              #在字典里加入major,
  #  "experience":experience_text,                     #在字典里加入experience
  #}
  #return detail_data                                  #输出



  



if __name__ == "__main__":
    #website = input("请输入要爬的网址：")                    #定义变量website，让用户输入要爬的网址(弃用)
    debug_url = "https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfomore.action"#有bug，加一个
    base_url = debug_url                                   #定义baseurl，保存网站主地址

    html = get_page(base_url)                              #调用函数
    job_list = parse_job_list(html, base_url)              #合成绝对链接，加入到joblist
    for job_data in job_list:                              #在职位列表里取出职位信息
         detail_url = job_data["detail_url"]                #在字典里用键detail_url 找值，赋值
         time.sleep(1)                                     #1s一次
         try:                                              #尝试运行，如果可以继续，不可以就运行except
            detail_html = get_page(detail_url)            #函数
            detail_data = parse_job_detail(detail_html)   #函数
            job_data.update(detail_data)                  #加入字典
            print(job_data["title"])
            print(job_data["education"])
            print(job_data["major"])
            print(job_data["detail_url"])
         except requests.exceptions.HTTPError:            #如果报错
            print("无存档")
         except requests.exceptions.SSLError:
            print("SSL连接失败，跳过")
    #print(job_list[0])
    # print(job_list)                                     #输出

    import os
    from pathlib import Path
    output_csv = os.environ.get("RECRUITMENT_CSV_PATH", str(Path(__file__).resolve().parent / "招聘数据.csv"))
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)#创建工具
        writer.writerow(["岗位名", "学历", "专业", "链接"])#写入表头
        for job_data in job_list:#循环写入
          writer.writerow([#写入
            job_data["title"],
            job_data.get("education", "none"),
            job_data.get("major", "none"),
            job_data["detail_url"]
        ])