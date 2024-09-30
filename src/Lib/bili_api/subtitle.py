from urllib.parse import urlsplit

from . import utils
import copy
import http.client
import json

from .exceptions import NetWorkException

API = utils.get_api(('subtitle',))


def get_subtitle_url(aid: int,
                     cid: int,
                     passport: utils.BiliPassport = None) -> str:
    if passport is None:
        return
    api = copy.deepcopy(API['subtile'])
    url = urlsplit(api['url'])
    params = api['params']
    params['aid'] = aid
    params['cid'] = cid

    header = {}
    if passport is not None:
        header['cookie'] = passport.get_cookie()

    get: dict = utils.network.get_data(
        scheme=url.scheme,
        host=url.netloc,
        method=api['method'],
        path=url.path,
        query=params,
        header=header
    )

    if get['code'] != 0:
        raise NetWorkException('字幕链接获取错误:\n{0};\n{1};\n{2}'.format(
            get['code'],
            api['return']['code'].get(str(get['code']), '未知错误'),
            get['message']
        ))
    return get['data']


def download_subtitle_url(url: str) -> dict:
    url_fix = "https://" + url
    url_ = urlsplit(url)

    header = {'referer': "https://www.bilibili.com/"}

    conn = http.client.HTTPSConnection(url_.netloc)
    conn.request(
        method='GET',
        url=url_.path + '?' + url_.query,
        headers=header
    )
    get = conn.getresponse()
    data = get.read()
    get.close()
    conn.close()
    data_string = data.decode('utf_8')
    json_data = json.loads(data_string)
    return json_data
