# Batch qualification of independent programs

This is a consolidated installer for the 16 currently reviewed standalone
recipes. It does not install every source file in the 24 repositories. The
remaining repository capabilities require individual source and license review,
native runtimes, dependencies, and functional fixtures. The batch status
command reports all 24 pinned repositories and partial coverage explicitly.

Use a dedicated test VM/host. Review the pinned upstream programs and existing
runtime definitions before executing. No repository code runs during review.
The batch uses only the existing local Python, document and Office Docker
images; it never pulls or builds images, changes production services, connects
brokers, installs native agent hosts, or deletes existing data. On another host,
prepare the three images using the documented recipe-specific instructions
first. Docker does not provide a complete boundary for hostile source.

From the independent manager checkout:

    python3 -m unittest discover -s tests -p 'test_independent*.py' -v
    python3 lab/batch_install.py status
    python3 lab/batch_install.py review

Inspect the exact plans and immutable local image IDs. Copy the printed
batch approval digest (do not auto-approve an unreviewed plan):

    python3 lab/batch_install.py install --approve REVIEWED_DIGEST
    python3 lab/batch_install.py status

Matching qualification receipts are skipped. Each failure is recorded, and
independent recipes continue; the command returns nonzero on any failure.
Batch reports are written to ~/core-ai-lab/reports/batches/. Interrupted
batches can be reviewed and resumed; qualified receipts remain in place.
An image or plan change invalidates the batch approval. Source checkouts
must be clean and pinned. A receipt records a prior fixture pass, not a
fresh execution or certification of every upstream capability.

Additional pure-Python programs:

    IMAGE=$(docker image inspect --format '{{.Id}}' python:3.12-slim)
    python3 lab/more_programs.py list
    python3 lab/more_programs.py run contract-sizing --image "$IMAGE" --params '[100000,0.01,100,95,0,0,25,1]'
    python3 lab/more_programs.py run trade-expectancy --image "$IMAGE" --params '[0.6,2,1]'
    python3 lab/more_programs.py run trade-statistics --image "$IMAGE" --params '[100,-50,150,-100]'
    python3 lab/more_programs.py run equity-drawdown --image "$IMAGE" --params '[100,120,90,110,130]'
    python3 lab/more_programs.py run option-greeks --image "$IMAGE" --params '[100,100,1,0.05,0.2,0]'
    python3 lab/more_programs.py run option-implied-vol --image "$IMAGE" --params '[10.450583572,100,100,1,0.05,"call",0]'
    python3 lab/more_programs.py run notebook-scaffold --image "$IMAGE" --params '["experiment","Strategy research"]' --output "$HOME/core-ai-lab/strategy-research.ipynb"

Notebook generation does not execute notebook cells or install Jupyter.
The notebook output must not exist. Financial examples are synthetic; no
live data or orders. Contract sizing assumes matching currency, verified
multipliers/lot increments and estimated friction; margin, liquidity,
portfolio exposure and gap risk are not included. Drawdown is negative
percentage from peak, not PnL units. Trade statistics use additive PnL,
and a mathematically infinite profit factor is represented as null.
Options use European Black-Scholes-Merton assumptions with continuous
dividend yield, annual rate/volatility decimals and time in years. Theta
is per calendar day, vega/rho per percentage point. Implied vol can be null
when a valid solution is not bracketed. These are research utilities, not
broker risk controls or trading recommendations.

The full trading-skills package from staskh requires Python >=3.13 and
additional dependencies; ML4T skill examples refer to separate ML4T libraries.
Those package/native-host installations, and all other unreviewed capabilities,
are not silently treated as installed by this batch.
