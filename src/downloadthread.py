import os
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from PySide6 import QtCore

from Lib.bili_api import video, danmaku, bangumi, subtitle
from Lib.bili_api.utils import BiliPassport
from Lib.xml2ass import convertMain
from Lib.bili_api.subtitle import get_subtitle_url, download_subtitle_url
from Lib.json2srt import json2srt
from utils import configUtils

_DEFAULT_HEADERS = {
    "Referer": "https://www.bilibili.com",
    "User-Agent": "Mozilla/5.0",
}


def download_danmaku(path, cid):
    danmakuXml = danmaku.get_danmaku_xml(cid)
    danmakuAss = convertMain(danmakuXml, 852, 480, text_opacity=0.6)
    with open(path, "w", encoding="utf_8") as f:
        f.write(danmakuAss)


def do_download_subtitle(path, aid, cid, passport):
    subtitle_data = get_subtitle_url(aid, cid, passport)
    sub_zh = ""
    sub_en = ""
    if len(subtitle_data['subtitle']["subtitles"]) > 0:
        for sub in subtitle_data['subtitle']['subtitles']:
            language = sub['lan']
            subtitle_url = sub['subtitle_url']
            if language == "zh-CN":
                sub_zh = subtitle_url
            elif language == "ai-zh" and sub_zh == "":
                sub_zh = subtitle_url
            if language == "en-US":
                sub_en = subtitle_url
            elif language == "ai-en" and sub_en == "":
                sub_en = subtitle_url
        if sub_zh != "":
            zh = download_subtitle_url(sub_zh)
            if zh:
                with open(path.replace('.srt', '.zh-CN.srt'), "w", encoding="utf_8") as f:
                    f.write(json2srt(zh))
        if sub_en != "":
            en = download_subtitle_url(sub_en)
            if en:
                with open(path.replace('.srt', '.en-US.srt'), "w", encoding="utf_8") as f:
                    f.write(json2srt(en))


class DownloadTask(QtCore.QThread):
    def __init__(self, parent: QtCore.QObject | None = ...) -> None:
        super().__init__(parent)
        self.fource_stop = False
        self.video_finished_size = 0
        self.audio_finished_size = 0
        self.total_size = 0
        self.task = None
        self.timer_stopped = False
        self.timer = None

    def setup(self, task: dict):
        self.task = task

    def t_stop(self):
        self.fource_stop = True

    def timer_timeout(self):
        self.emit(
            QtCore.SIGNAL("update_progress(quint64, quint64)"),
            self.video_finished_size + self.audio_finished_size,
            self.total_size,
        )
        if self.video_finished_size + self.audio_finished_size == self.total_size and self.total_size != 0:
            self.timer.stop()
            self.timer_stopped = True

    def download_dash(self, get_url: dict, root_dir: QtCore.QDir):
        video_urls: list = get_url["dash"]["video"]
        video_urls.sort(key=lambda x: x["id"], reverse=True)
        quality = self.task["quality"]
        codec = self.task["codec"]
        if quality > video_urls[0]["id"]:
            quality = video_urls[0]["id"]
        qid_match = []
        for i in video_urls:
            if i["id"] == quality:
                qid_match.append(i)
        qid_match.sort(key=lambda x: x["codecid"])
        video_url = qid_match[0]["baseUrl"]
        for i in qid_match:
            if i["codecid"] == codec:
                video_url = i["baseUrl"]
        audio_url = get_url["dash"]["audio"][0]["baseUrl"]

        # Get size
        try_times = 0
        while try_times < 3:
            try:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "正在获取视频流信息")
                req = Request(url=video_url, method="GET", headers=_DEFAULT_HEADERS)
                with urlopen(req) as resp:
                    video_size = int(resp.headers["content-length"])
                req = Request(url=audio_url, method="GET", headers=_DEFAULT_HEADERS)
                with urlopen(req) as resp:
                    audio_size = int(resp.headers["content-length"])
                break
            except Exception as _e:
                try_times += 1
                self.emit(
                    QtCore.SIGNAL("update_status(QString)"),
                    "获取视频信息失败，即将重试，次数{}".format(try_times),
                )
                time.sleep(2)
        else:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
            self.task["finished"] = True
            return
        self.total_size = video_size + audio_size
        self.video_finished_size = 0
        self.audio_finished_size = 0

        self.emit(QtCore.SIGNAL("enable_restart()"))

        # Download video
        req = Request(url=video_url, method="GET", headers=_DEFAULT_HEADERS)
        video_temp_file_name = "{}_temp.mp4".format(self.task["name"])
        video_temp_file_path = root_dir.absoluteFilePath(video_temp_file_name)
        try_times = 0
        while try_times < 3:
            try:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "正在下载视频")
                with open(video_temp_file_path, "wb") as f:
                    with urlopen(req) as resp:
                        while True:
                            buffer = resp.read(4096)
                            if self.fource_stop:
                                return
                            if not buffer:
                                break
                            f.write(buffer)
                            self.video_finished_size += len(buffer)
                break
            except Exception as _e:
                try_times += 1
                self.emit(
                    QtCore.SIGNAL("update_status(QString)"),
                    "下载视频失败，即将重试，次数{}".format(try_times),
                )
                time.sleep(2)
        else:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
            self.task["finished"] = True
            return

        # Download audio
        req = Request(url=audio_url, method="GET", headers=_DEFAULT_HEADERS)
        audio_temp_file_name = "{}_temp.m4a".format(self.task["name"])
        audio_temp_file_path = root_dir.absoluteFilePath(audio_temp_file_name)
        try_times = 0
        while try_times < 3:
            try:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "正在下载音频")
                with open(audio_temp_file_path, "wb") as f:
                    with urlopen(req) as resp:
                        while True:
                            buffer = resp.read(4096)
                            if self.fource_stop:
                                return
                            if not buffer:
                                break
                            f.write(buffer)
                            self.audio_finished_size += len(buffer)
                break
            except Exception as _e:
                try_times += 1
                self.emit(
                    QtCore.SIGNAL("update_status(QString)"),
                    "下载音频失败，即将重试，次数{}".format(try_times),
                )
                time.sleep(2)
        else:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
            self.task["finished"] = True
            return

        # End Download
        while not self.timer_stopped:
            time.sleep(0.1)

        # ffmpeg
        self.emit(QtCore.SIGNAL("update_status(QString)"), "正在使用ffmpeg合并")
        out_name = "{}.mp4".format(self.task["name"])
        if root_dir.exists(out_name):
            root_dir.remove(out_name)
        ffmpeg_path = QtCore.QDir("ffmpeg").absoluteFilePath("ffmpeg" + ("" if sys.platform == "linux" else ".exe"))
        devnull = open(os.devnull, "w")
        if sys.platform == "linux":
            subprocess.call(
                [
                    ffmpeg_path,
                    "-i",
                    video_temp_file_path,
                    "-i",
                    audio_temp_file_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    root_dir.absoluteFilePath(out_name),
                ],
                stdout=devnull,
                stderr=devnull,
            )
        else:
            subprocess.call(
                [
                    ffmpeg_path,
                    "-i",
                    video_temp_file_path,
                    "-i",
                    audio_temp_file_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    root_dir.absoluteFilePath(out_name),
                ],
                stdout=devnull,
                stderr=devnull,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        devnull.close()

        # Cleanup
        self.emit(QtCore.SIGNAL("update_status(QString)"), "正在清理")
        root_dir.remove(video_temp_file_path)
        if self.task["reserveAudio"]:
            root_dir.rename(audio_temp_file_name, "{}.m4a".format(self.task["name"]))
        else:
            root_dir.remove(audio_temp_file_path)

    def download_mp4(self, get_url: dict, root_dir: QtCore.QDir):
        video_urls: list = get_url["durls"]
        video_urls.sort(key=lambda x: x["quality"], reverse=True)
        quality = self.task["quality"]
        if quality > video_urls[0]["quality"]:
            quality = video_urls[0]["quality"]
        qid_match = []
        for i in video_urls:
            if i["quality"] == quality:
                qid_match.append(i)
        video_url = qid_match[0]["durl"][0]["url"]

        # Get size
        try_times = 0
        while try_times < 3:
            try:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "正在获取视频流信息")
                req = Request(url=video_url, method="GET", headers=_DEFAULT_HEADERS)
                with urlopen(req) as resp:
                    video_size = int(resp.headers["content-length"])
                break
            except Exception as _e:
                try_times += 1
                self.emit(
                    QtCore.SIGNAL("update_status(QString)"),
                    "获取视频信息失败，即将重试，次数{}".format(try_times),
                )
                time.sleep(2)
        else:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
            self.task["finished"] = True
            return
        self.total_size = video_size
        self.video_finished_size = 0
        self.audio_finished_size = 0

        self.emit(QtCore.SIGNAL("enable_restart()"))

        # Download video
        req = Request(url=video_url, method="GET", headers=_DEFAULT_HEADERS)
        video_temp_file_name = "{}_temp.mp4".format(self.task["name"])
        video_temp_file_path = root_dir.absoluteFilePath(video_temp_file_name)
        try_times = 0
        while try_times < 3:
            try:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "正在下载视频")
                with open(video_temp_file_path, "wb") as f:
                    with urlopen(req) as resp:
                        while True:
                            buffer = resp.read(4096)
                            if self.fource_stop:
                                return
                            if not buffer:
                                break
                            f.write(buffer)
                            self.video_finished_size += len(buffer)
                break
            except Exception as _e:
                try_times += 1
                self.emit(
                    QtCore.SIGNAL("update_status(QString)"),
                    "下载视频失败，即将重试，次数{}".format(try_times),
                )
                time.sleep(2)
        else:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
            self.task["finished"] = True
            return
        root_dir.rename(video_temp_file_name, "{}.mp4".format(self.task["name"]))

    def download_danmaku(self, root_dir: QtCore.QDir):
        danmaku_file_name = "{}.ass".format(self.task["name"])
        try:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "正在下载弹幕")
            download_danmaku(
                root_dir.absoluteFilePath(danmaku_file_name), self.task["cid"]
            )
        except Exception as _:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "弹幕下载失败，已跳过")
            if root_dir.exists(danmaku_file_name):
                root_dir.remove(danmaku_file_name)
            time.sleep(1)

    def download_subtitle(self, root_dir: QtCore.QDir, passport):
        subtitles_file_name = "{}.srt".format(self.task["name"])
        try:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "正在下载字幕")
            do_download_subtitle(
                root_dir.absoluteFilePath(subtitles_file_name), self.task["aid"], self.task["cid"], passport
            )
        except Exception as _:
            self.emit(QtCore.SIGNAL("update_status(QString)"), "下载字幕失败或字幕不存在，已跳过")
            if root_dir.exists(subtitles_file_name):
                root_dir.remove(subtitles_file_name)
            time.sleep(1)

        pass

    def run(self):
        self.emit(QtCore.SIGNAL("update_status(QString)"), "开始下载")

        # Creat directory
        root_dir = QtCore.QDir(self.task["path"])
        if not root_dir.exists(self.task["title"]):
            root_dir.mkdir(self.task["title"])
        root_dir.cd(self.task["title"])

        # Load Passport
        passportRaw = configUtils.getUserData(configUtils.Configs.PASSPORT)
        passport = None
        if passportRaw is not None:
            passportRaw = passportRaw["data"]
            passportRaw.pop("Expires")
            passport = BiliPassport(passportRaw)

        # Get Urls
        if self.task["saveVideo"]:
            try_times = 0
            while try_times < 3:
                try:
                    self.emit(QtCore.SIGNAL("update_status(QString)"), "正在获取链接")
                    get_url = None
                    if self.task["type"] == "video":
                        if self.task["isbvid"]:
                            get_url = video.get_video_url(
                                bvid=self.task["id"], cid=self.task["cid"], fnval=self.task["fnval"], passport=passport
                            )
                        else:
                            get_url = video.get_video_url(
                                avid=self.task["id"], cid=self.task["cid"], fnval=self.task["fnval"], passport=passport
                            )
                    elif self.task["type"] == "bangumi":
                        if self.task["isbvid"]:
                            get_url = bangumi.get_bangumi_url(
                                bvid=self.task["id"],
                                cid=self.task["cid"],
                                fnval=self.task["fnval"],
                                passport=passport,
                            )["video_info"]
                        else:
                            get_url = bangumi.get_bangumi_url(
                                avid=self.task["id"],
                                cid=self.task["cid"],
                                fnval=self.task["fnval"],
                                passport=passport,
                            )["video_info"]
                    break
                except Exception as _e:
                    try_times += 1
                    self.emit(
                        QtCore.SIGNAL("update_status(QString)"),
                        "获取链接失败，即将重试，次数{}".format(try_times),
                    )
                    if try_times >= 3 and self.task["type"] == "video":
                        self.emit(
                            QtCore.SIGNAL("update_status(QString)"),
                            "失败次数过多，尝试更换获取链接方式"
                        )
                        time.sleep(1.0)
                        self.task["type"] = "bangumi"
                        try_times = 0
                    time.sleep(2)
            else:
                self.emit(QtCore.SIGNAL("update_status(QString)"), "下载失败，请重新输入")
                self.task["finished"] = True
                return

            self.timer = QtCore.QTimer()
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.timer_timeout)
            self.timer_stopped = False
            self.timer.start()
            self.timer.moveToThread(self.thread())

            # parse urls
            if self.task["type"] == "video":
                self.download_dash(get_url, root_dir)
            elif self.task["type"] == "bangumi":
                if get_url["type"] == "DASH":
                    self.download_dash(get_url, root_dir)
                elif get_url["type"] == "MP4":
                    self.download_mp4(get_url, root_dir)

        if self.fource_stop:
            return

        # Download and parse subtitles
        if self.task["saveSubtitle"]:
            self.download_subtitle(root_dir, passport)

        # Download and parse Xml Danmaku
        if self.task["saveDanmu"]:
            self.download_danmaku(root_dir)

        time.sleep(0.2)

        self.emit(QtCore.SIGNAL("update_status(QString)"), "下载完成")
        self.emit(QtCore.SIGNAL("update_finished()"))
        self.task["finished"] = True
