"""
真实文件名识别测试
基于 /Volumes/影音库/电影 中的实际文件名，验证 MediaIdentifier 的识别能力。
测试分为两类：
- 预期能识别：断言 media_type 和 year 正确
- 已知识别不足：只断言不返回 None，记录实际识别结果供分析
"""
import pytest
from core.identifier import MediaIdentifier


@pytest.fixture
def identifier():
    return MediaIdentifier()


class TestRealWorldMovieFiles:
    """能正确识别年份的文件名"""

    @pytest.mark.parametrize("path,expected_year", [
        # 纯英文点分隔 + 年份
        ("/电影/Top.Gun.1986.2160p.UHD.BluRay.x265/Top.Gun.1986.2160p.UHD.BluRay.x265.mkv", 1986),
        ("/电影/阿凡达/Avatar.The.Way.Of.Water.2022.PROPER.Bluray.2160p.AV1.mkv", 2022),
        ("/电影/波西米亚狂想曲/Bohemian.Rhapsody.2018.2160p.BluRay.REMUX.HEVC.mkv", 2018),
        ("/电影/海王/Aquaman.2018.IMAX.2160p.BluRay.REMUX.HEVC.mkv", 2018),
        ("/电影/绿皮书/Green.Book.2018.2160p.BluRay.REMUX.HEVC.mkv", 2018),
        ("/电影/生死狙击/Shooter.2007.2160p.AMZN.WEB-DL.x265.mkv", 2007),
        ("/电影/肖申克的救赎/The.Shawshank.Redemption.1994.2160p.BluRay.x265.mkv", 1994),
        ("/电影/2012/2012.2009.2160p.BluRay.x264.8bit.SDR.mkv", 2009),
        ("/电影/蜘蛛侠1/Spider-Man.2002.2160p.BluRay.REMUX.HEVC.mkv", 2002),
        ("/电影/蜘蛛侠2/Spider-Man.2.2004.2160p.BluRay.REMUX.HEVC.mkv", 2004),
        ("/电影/蜘蛛侠3/Spider-Man.3.2007.2160p.BluRay.REMUX.HEVC.mkv", 2007),
        ("/电影/蜘蛛侠英雄无归/Spider-Man.No.Way.Home.2021.UHD.BluRay.2160p.mkv", 2021),
        ("/电影/哥斯拉/哥斯拉.Godzilla.1998.BluRay.2160p.x265.mkv", 1998),
        ("/电影/哥斯拉2/哥斯拉2：怪兽之王.Godzilla.King.of.the.Monsters.2019.BluRay.2160p.mkv", 2019),
        ("/电影/哥斯拉大战金刚/哥斯拉大战金刚.Godzilla.vs.Kong.2021.BluRay.2160p.mkv", 2021),
        ("/电影/F1/F1.The.Movie.2025.Hybrid.2160p.WEB-DL.mkv", 2025),
    ])
    def test_year_extracted_correctly(self, identifier, path, expected_year):
        q = identifier.identify(path)
        assert q is not None
        assert q.media_type == "movie"
        assert q.year == expected_year, f"文件名: {path}\n实际识别: title={q.title!r}, year={q.year}"


class TestRealWorldEdgeCases:
    """已知识别困难的文件名，记录实际结果"""

    @pytest.mark.parametrize("path,note", [
        # 纯中文文件名，无年份
        ("/电影/爆裂鼓手/爆裂鼓手.mkv", "纯中文，无年份"),
        ("/电影/环太平洋/环太平洋.mkv", "纯中文，无年份"),
        ("/电影/惊奇队长/惊奇队长.mkv", "纯中文，无年份"),
        ("/电影/雷神/雷神1.mkv", "纯中文+序号，无年份"),
        ("/电影/雷神/雷神2_黑暗世界.mkv", "纯中文+序号+下划线，无年份"),
        ("/电影/雷神/雷神3_诸神黄昏.mkv", "纯中文+序号+下划线，无年份"),
        # 中英混合，年份在中间
        ("/电影/复仇者联盟/复仇者联盟1.The.Avengers.IMAX.2012.国语.50.4G.mkv", "中英混合，年份在中间"),
        ("/电影/复仇者联盟/复仇者联盟2.奥创纪元.Avengers.Age.of.Ultron.2015.国语.mkv", "中英混合，年份在中间"),
        ("/电影/复仇者联盟/复仇者联盟3.无限战争.Avengers.Infinity.War.2018.国语.mkv", "中英混合，年份在中间"),
        ("/电影/复仇者联盟/复仇者联盟4.终局之战.Avengers.Endgame.2019.国语.mkv", "中英混合，年份在中间"),
        ("/电影/钢铁侠/钢铁侠1_Iron.Man.01.2008_国语_56.6G.mkv", "中英混合+下划线分隔"),
        ("/电影/钢铁侠/钢铁侠2_Iron.Man.02.2010_国语_52.7G.mkv", "中英混合+下划线分隔"),
        ("/电影/银河护卫队/银河护卫队1Guardians.Of.The.Galaxy.Vol.1.2014_国语_47.2G.mkv", "中英直接拼接"),
        # 空格分隔
        ("/电影/超人2025/Superman 2025 2160p iT WEB-DL DDP5 1 Atmos DV HDR H 265-BYNDR.mkv", "空格分隔，年份紧跟标题"),
        ("/电影/美国队长/美国队长4.2025.2160p.WEB-DL.DD5.1.H264.mkv", "中文+序号+年份"),
        # 中括号
        ("/电影/死亡笔记/死亡笔记Death.Note.2006.BluRay.720p.x264[中文字幕3.8G].mkv", "含中括号"),
        ("/电影/死亡笔记/L改变世界.Change.the.World.2008.BluRay.720p.x264[中文字幕4G].mkv", "含中括号"),
        # 蜘蛛侠系列
        ("/电影/蜘蛛侠英雄归来/蜘蛛侠 英雄归来_Spider-Man.Homecoming.2017_国语_52.9G.mkv", "中文空格+下划线混合"),
        ("/电影/蜘蛛侠英雄远征/蜘蛛侠 英雄远征_Spider-Man.Far.from.Home.2019_国语_54.6G.mkv", "中文空格+下划线混合"),
    ])
    def test_edge_cases_report(self, identifier, path, note):
        """不强制断言 year，只打印识别结果供分析"""
        q = identifier.identify(path)
        assert q is not None, f"[{note}] 应至少识别为 movie，但返回了 None"
        # 打印实际识别结果，方便分析
        print(f"\n[{note}]\n  文件名: {path.split('/')[-1]}\n  title={q.title!r}, year={q.year}")
