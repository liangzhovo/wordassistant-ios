# -*- coding: utf-8 -*-
"""FSRS 间隔重复调度器（移植自 FSRS4Anki v6.1.1 官方调度器）。

来源：https://github.com/open-spaced-repetition/fsrs4anki  fsrs4anki_scheduler.js
本文件只移植「调度核心」（纯函数，无 Anki 依赖）；
排序选择在 app.py 的 /api/review 中使用。

评分映射（本应用交互只有 答对/答错+忘记 两档）：
  correct=True   -> good(3)
  correct=False  -> again(1)
hard(2)/easy(4) 保留接口（future UI 可扩展四档）。

字段：stability(S)、difficulty(D)、reviewed_at（上次复习时间）。
可提取性 R(t) = forgetting_curve(elapsed_days, S)，用于复习队列排序。
"""
import math

W = [0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001,
     1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
     1.8729, 0.5425, 0.0912, 0.0658, 0.1542]

REQUEST_RETENTION = 0.9
MAXIMUM_INTERVAL = 36500  # 天

RATINGS = {'again': 1, 'hard': 2, 'good': 3, 'easy': 4}

DECAY = -W[20]
FACTOR = 0.9 ** (1 / DECAY) - 1

INIT_S = {'again': max(W[0], 0.1), 'hard': max(W[1], 0.1),
          'good': max(W[2], 0.1), 'easy': max(W[3], 0.1)}


def _constrain_difficulty(d):
    return min(max(round(d, 2), 1), 10)


def _linear_damping(delta_d, old_d):
    return delta_d * (10 - old_d) / 9


def _mean_reversion(init, current):
    return W[7] * init + (1 - W[7]) * current


def init_difficulty(rating):
    """rating: 'again'|'hard'|'good'|'easy'"""
    return round(_constrain_difficulty(
        W[4] - math.exp(W[5] * (RATINGS[rating] - 1)) + 1), 2)


def init_stability(rating):
    return round(max(W[RATINGS[rating] - 1], 0.1), 2)


def forgetting_curve(elapsed_days, stability):
    """返回可提取性 R（0~1）。elapsed_days 为距上次复习的天数（可为小数）。"""
    if stability <= 0 or elapsed_days < 0:
        return 1.0
    return (1 + FACTOR * elapsed_days / stability) ** DECAY


def next_interval(stability):
    """下一次复习间隔（天）；省略官方 fuzz 随机抖动（保持确定性，便于测试）。"""
    ivl = stability / FACTOR * (REQUEST_RETENTION ** (1 / DECAY) - 1)
    return int(min(max(round(ivl), 1), MAXIMUM_INTERVAL))


def next_difficulty(d, rating):
    delta_d = -W[6] * (RATINGS[rating] - 3)
    nxt = d + _linear_damping(delta_d, d)
    return round(_constrain_difficulty(_mean_reversion(init_difficulty('easy'), nxt)), 2)


def next_recall_stability(d, s, r, rating):
    """答对后的新稳定性。r 为作答时的可提取性 R(t)。"""
    hard_penalty = W[15] if rating == 'hard' else 1
    easy_bonus = W[16] if rating == 'easy' else 1
    return round(s * (1 + math.exp(W[8]) * (11 - d) * (s ** (-W[9])) *
                      (math.exp((1 - r) * W[10]) - 1) * hard_penalty * easy_bonus), 2)


def next_forget_stability(d, s, r):
    """答错/忘记后的新稳定性。"""
    s_min = s / math.exp(W[17] * W[18])
    return round(min(W[11] * (d ** (-W[12])) * ((s + 1) ** W[13] - 1) *
                     math.exp((1 - r) * W[14]), s_min), 2)


def next_short_term_stability(s, rating):
    """短时稳定性（学习/重学状态）。"""
    sinch = math.exp(W[17] * (RATINGS[rating] - 3 + W[18])) * (s ** (-W[19]))
    if RATINGS[rating] >= 3:
        sinch = max(sinch, 1)
    return round(s * sinch, 2)


def schedule(correct, stability, difficulty, elapsed_days):
    """一次作答后的调度更新（应用全部词汇复用此入口）。

    参数：
      correct      答对 True / 答错或忘记 False
      stability    作答前稳定性 S（新词传 None）
      difficulty   作答前难度 D（新词传 None）
      elapsed_days 距上次复习天数（新词传 0）
    返回：
      (new_s, new_d, interval_days)
    """
    rating = 'good' if correct else 'again'
    if stability is None or difficulty is None:
        new_s = init_stability(rating)
        new_d = init_difficulty(rating)
    else:
        r = forgetting_curve(elapsed_days, stability)
        if correct:
            new_s = next_recall_stability(difficulty, stability, r, rating)
        else:
            new_s = next_forget_stability(difficulty, stability, r)
        new_d = next_difficulty(difficulty, rating)
    return new_s, new_d, next_interval(new_s)