# Independent financial calculation programs

Four MIT-licensed upstream scripts at agiprolabs/claude-trading-skills
commit 981e1d736cdc02bdc1c55c74ec9224e956414706. They use the Python
standard library; reuse the qualified local Python 3.12 image. No broker,
credentials, network, or CORE-AI service is needed. Review source and
plans in a dedicated test environment before execution.

    IMAGE=$(docker image inspect --format '{{.Id}}' python:3.12-slim)
    python3 lab/trading_programs.py list
    python3 lab/trading_programs.py review position-sizing --image "$IMAGE"

Repeat review for kelly-criterion, black-scholes and bond-pricing. Copy the
actual digest from each reviewed plan into its install command:

    python3 lab/trading_programs.py install position-sizing --image "$IMAGE" --approve DIGEST

Run with explicit numeric parameters in the listed order:

    python3 lab/trading_programs.py run position-sizing --image "$IMAGE" --params '[10000,0.01,100,95,0,0]'
    python3 lab/trading_programs.py run kelly-criterion --image "$IMAGE" --params '[0.6,2]'
    python3 lab/trading_programs.py run black-scholes --image "$IMAGE" --params '[100,100,1,0.05,0.2]'
    python3 lab/trading_programs.py run bond-pricing --image "$IMAGE" --params '[1000,0.05,0.05,20,2]'

Each recipe validates a synthetic known-answer fixture before recording a
receipt. These are not live-market data or recommendations. The upstream
options and bond modules label themselves as stubs; numeric fixture success
does not establish broad production accuracy. Black-Scholes assumes a
European option without dividends; rate and volatility are annual decimals,
time is years. Theta is per calendar day; vega/rho per percentage point.
The AGIPro normal CDF documents maximum absolute approximation error
7.5e-8. Only its premium fixture uses the propagated absolute bound
7.5e-8 * (spot + discounted strike) + 1e-9 for reference rounding.
Put-call parity and the original Greek invariants use the strict existing
comparison. Other recipes retain their original qualification digests.
This verifies a fixture, not accuracy across all market conditions.
Bond pricing assumes regular coupon periods and no default or call risk.
Sizing uses one currency, unit price distance, fees and estimated slippage;
it is not a broker quantity and ignores margin, contract multipliers,
lot rounding, exposure and gap risk. The full upstream combined sizing
report discards zero candidates, including no-edge Kelly; this recipe
deliberately exposes the fixed-fractional calculation only. Do not use
the raw calculators as pre-trade risk controls. Kelly depends on estimated
win probability and payoff and can be negative. Other upstream functions
and execution integrations remain available for later review; no orders
are placed by this recipe.

Tests: python3 -m unittest discover -s tests -p 'test_independent*.py' -v
