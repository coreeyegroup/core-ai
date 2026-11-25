# Offline quantitative analysis batch

Six new recipes use the original pinned upstream Python modules. TradeKit
technical indicators and Monte Carlo reuse Python 3.12. Four additional
recipes use the shared quant image. Staskh's isolated Black-Scholes module
is tested under Python 3.12; its full package requires Python >=3.13 and
is not installed here. All three source repositories have MIT licenses.
Backtrader is a separately installed dependency (GPL); retain applicable
license notices and review redistribution obligations.

Build only after reviewing the Dockerfile and dependencies on a test host:

    docker build -t core-ai-lab-quant:0.1.0 lab/runtime/quant
    docker run --rm --network none core-ai-lab-quant:0.1.0 python -m pip check

Versions are selected for compatibility with Python 3.12 and older
upstream examples, not claimed to be latest or vulnerability-free.
The base image and dependency versions are pinned, but not wheel hashes.
No host package changes, broker access or live market requests.

    python3 lab/batch_install.py review
    python3 lab/batch_install.py install --approve REVIEWED_DIGEST
    python3 lab/batch_install.py status

All 22 currently reviewed recipes are included; existing receipts remain
valid except the previously failed AGIPro Black-Scholes fixture which was
corrected separately. Use the exact displayed batch digest after review.

    python3 lab/quant_programs.py list
    PY_IMAGE=$(docker image inspect --format '{{.Id}}' python:3.12-slim)
    Q_IMAGE=$(docker image inspect --format '{{.Id}}' core-ai-lab-quant:0.1.0)
    python3 lab/quant_programs.py run technical-indicators --image "$PY_IMAGE" --params '[[1,2,3,4,5],3]'
    python3 lab/quant_programs.py run monte-carlo --image "$PY_IMAGE" --params '[[1,-1,2,-1,1],1,50,500,10000,7]'
    python3 lab/quant_programs.py run correlation-matrix --image "$Q_IMAGE" --params '[[1,2,3,4],[2,4,6,8]]'
    python3 lab/quant_programs.py run numpy-drawdown --image "$Q_IMAGE" --params '[100,120,90,110,130]'
    python3 lab/quant_programs.py run scipy-option-price --image "$Q_IMAGE" --params '[100,100,1,0.05,0.2,0]'
    python3 lab/quant_programs.py run ema-backtest --image "$Q_IMAGE" --params '[3,8,10000,0.001,0.001,1,42,120,[]]'

Backtest parameters: fast EMA, slow EMA, cash, commission per side as
fraction, slippage as fraction, fixed units, seed, synthetic days, and
optional historical OHLCV rows. Rows are [ISO timestamp,open,high,low,close,
volume], ordered, unique and timezone-naive. A nonempty row array replaces
the synthetic dataset. Use --params-file for larger JSON inputs; limits
are 500 OHLCV rows and 36,000 serialized characters. Inputs are transmitted
as command arguments; do not include secrets or confidential data.
The wrapper uses the original EMA crossover strategy, a simulated
Backtrader broker, fixed units, and normal next-bar execution (no
cheat-on-open). It has no stop-loss or live risk controls and can hold an
open position at the end; final equity includes mark-to-market.
This is a qualification and research example, not a strategy recommendation.
Monte Carlo resamples observed R values and assumes those values are
representative; risk percent is in percent points, not decimal fraction.
Correlation inputs must be synchronized returns, not prices. Drawdown
from NumPy is a positive fraction; its upstream analyzer ignores periods
shallower than its default minimum depth (1%). Technical indicators
retain warm-up nulls. SciPy option pricing is European with continuous
dividend yield; rates and volatility are annual decimals, maturity years.

The full native packages, live providers, ML4T libraries, and remaining
agent-host integrations still require separate review and qualification.
