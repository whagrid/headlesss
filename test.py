import asyncio
import time
import re
import json
import threading
from queue import Queue
from lib.RedisUtil import RedisConf,RedisUtils
# from bs4 import BeautifulSoup as bs
from lib.headlesscrower import HeadlessCrawler
from lib.commons import TURL, hashmd5
from lib.UrlDeDuplicate import UrlPattern
#from pyppeteer.network_manager import Request


async def worker(redis_util, wsaddr, cookie=None, domain=''):
    while True:
        # 退出条件？如果用广度优先遍历，那么深度到一定程序如4层，就可以退出了
        # 或者redis的任务为0了,就可以退出了
        if redis_util.task_counts == 0:
            break
        # if unscan_queue.empty():
        #     break
        task = redis_util.fetch_one_task()
        # task = unscan_queue.get()
        url = json.loads(task)
        # 同源
        u = url['url']
        print("fetched Form Redis: {}".format(u))
        if not sameOrigin(u, domain):
            continue
        
        depth = url['depth']
        if depth > 3: # 超过四层就退出
            print("---------------depth > 3-------------")
            continue


        a = HeadlessCrawler(wsaddr, u, cookie=cookie, depth=url['depth']+1)
        await a.spider()
        for url in a.collect_url:
            u = url['url']

            if not sameOrigin(u, domain):
                continue
            pattern = UrlPattern(u).get_pattern()
            pattern_md5 = hashmd5(pattern)
            method = url['method']

            if 'request' in url:
                result = json.dumps(url)
                # # 插入结果，后续可以直接插入到Mongo里
                redis_util.insert_result(result)
                redis_util.set_url_scanned(method, pattern_md5)
            else:
                if redis_util.is_url_scanned(method, pattern_md5):
                    pass
                else:
                    task = json.dumps(url)
                    redis_util.insert_one_task(task)
                    redis_util.set_url_scanned(method, pattern_md5)
                # unscan_queue.put(task)
                # scanned_set.add( pattern + "|" + pattern_md5)



def sameOrigin(url, domain):
    try:
        turl = TURL(url)
        assert turl.netloc == domain, '{} is not belongs {}'.format(url, domain)
        assert turl.is_block_host() == False, '{} is block host'.format(url)
        assert turl.is_block_path() == False, '{} is block path'.format(url)
        assert turl.is_ext_static() == False, '{} is static extention'.format(url)
        return True
    except Exception as e:
        print(e)
        return False


async def spider(wsaddr, url, taskname, cookie=None, goon=False):
    # 2018-07-09 先写单线程，再写成生产者和消费者
    conf = RedisConf(taskname, db=1)
    redis_util = RedisUtils(conf)
    unscan_queue = Queue()
    result_queue = Queue()
    scanned_set = set()
    domain = TURL(url).netloc
    # count = 0
    # 设置domain
    redis_util.set_task_domain(domain)

    if not goon:
        print("start from new url.....")
        a = HeadlessCrawler(wsaddr, url, cookie=cookie)
        await a.spider()
        # print(a.collect_url)
        for url in a.collect_url:
            # 还可以判断一下url的类型
            u = url['url']
            # 先判断是否是同一个域名下的
            if not sameOrigin(u, domain):
                continue

            pattern = UrlPattern(u).get_pattern()
            pattern_md5 = hashmd5(pattern)
            if 'request' in url:
                result = json.dumps(url)
                method = url['method']
                # 插入结果，后续可以直接插入到Mongo里
                redis_util.insert_result(result)
                redis_util.set_url_scanned(method, pattern_md5)
            else:
                if redis_util.is_url_scanned(method, pattern_md5):
                    pass
                else:
                    task = json.dumps(url)
                    redis_util.insert_one_task(task)
                    redis_util.set_url_scanned(method, pattern_md5)

    '''
    in_loop = asyncio.get_event_loop()
    in_loop.run_until_complete(asyncio.gather(*[worker(conf, wsaddr, cookie) for t in range(10)]))
    in_loop.close()
    '''
    for i in range(20):
        # 20协程来跑
        await worker(redis_util, wsaddr, cookie, domain=domain)

    # while True:
    #     # 退出条件？如果用广度优先遍历，那么深度到一定程序如4层，就可以退出了
    #     # 或者redis的任务为0了,就可以退出了
    #     if redis_util.task_counts == 0:
    #         break
    #     # if unscan_queue.empty():
    #     #     break
    #     task = redis_util.fetch_one_task()
    #     # task = unscan_queue.get()
    #     url = json.loads(task)
    #     # 同源
    #     u = url['url']
    #     if not sameOrigin(u, domain):
    #         continue


    #     a = HeadlessCrawler(wsaddr, u, cookie=cookie, depth=url['depth']+1)
    #     await a.spider()
    #     for url in a.collect_url:
    #         # 还可以判断一下url的类型
    #         depth = url['depth']
    #         if depth > 3: # 超过四层就退出
    #             print("---------------depth > 3-------------")
    #             continue

    #         u = url['url']

    #         if not sameOrigin(u, domain):
    #             continue


    #         pattern = UrlPattern(u).get_pattern()
    #         pattern_md5 = hashmd5(pattern)
    #         method = url['method']

    #         if 'request' in url:
    #             result = json.dumps(url)
    #             # # 插入结果，后续可以直接插入到Mongo里
    #             redis_util.insert_result(result)
    #             redis_util.set_url_scanned(method, pattern_md5)
    #         else:
    #             if redis_util.is_url_scanned(method, pattern_md5):
    #                 pass
    #             else:
    #                 task = json.dumps(url)
    #                 redis_util.insert_one_task(task)
    #                 redis_util.set_url_scanned(method, pattern_md5)
    #             # unscan_queue.put(task)
    #             # scanned_set.add( pattern + "|" + pattern_md5)

    print("-----------done------")



async def test(wsaddr, url):
    # 2018-07-09 先写单线程，再写成生产者和消费者
    request_set = Queue()
    pattern_set = set()
    unrequest_set = Queue()

    a = HeadlessCrawler(wsaddr, url)
    await a.spider()
    # print(a.collect_url)
    for url in a.collect_url:
        # u = url['url']
        # u = TURL(u)
        # if u.is_ext_static() or u.is_block_path() or u.is_block_host():
        #     # 静态文件，黑名单路径，黑名单的host
        #     continue
        # pattern = get_pattern(u)
        # if pattern in pattern_set:
        #     continue
        # else:
        #     pattern_set.add(pattern)
        # if 'request' in url:
        #     request_set.put(url)
        # else:
        await unrequest_set.put(url)

    depth = 0
    print("[now] [lenth of unrequest_set] =======  {}".format(unrequest_set.qsize()))
    while not unrequest_set.empty():
        # print("[now] [lenth of unrequest_set] =======  {}".format(unrequest_set.qsize()))
        url = await unrequest_set.get()
        depth = int(url['depth'])
        if depth > 3:
            continue
        else:
            depth += 1
        url = url['url']
        pattern = get_pattern(url)
        if pattern in pattern_set:
            print("found pattern, igore URL： {}".format(u))
            continue
        else:
            pattern_set.add(pattern)


        a = HeadlessCrawler(wsaddr, url, depth=depth)
        await a.spider()
        print("===========================================\n")
        print("url: {}".format(url))
        print("len_of_a.collect_url:  {}".format(len(a.collect_url)))
        print("===========================================\n")
        for url in a.collect_url:
            u = url['url']
            if u.startswith('javascript') or u.startswith("about"):
                continue
            u = TURL(u)
            if u.is_ext_static():
                print("u.is_ext_static: {}".format(u))
                continue
            elif u.is_block_path():
                print("u.is_block_path: {}".format(u))
                continue
            elif u.is_block_host():
                print("u.is_block_host: {}".format(u))
                continue


            # print('pattern==={}'.format(pattern))
            if 'request' in url:
                await request_set.put(url)
                print("[now] [lenth of request_set] =======  {}".format(request_set.qsize()))
            else:
                await unrequest_set.put(url)



    print("========done=========")
    all_url = []
    while not request_set.empty():
        _ = await request_set.get()
        all_url.append(_)

    with open('result.json', 'w') as f:
        json.dump(all_url, f)







async def main():
    wsaddr = 'ws://10.127.21.237:9223/devtools/browser/d7707dac-b9c1-4397-bdbd-9ae147f4cfc8'
    url = 'http://www.iqiyi.com/'
    # with open('fetched_url.json', 'w') as f:
    #     json.dump((a.fetched_url), f)
    await spider(wsaddr, url, 'iqiyi', goon=False)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
