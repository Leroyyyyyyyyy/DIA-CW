from dataclasses import dataclass, field


@dataclass(slots=True)
class DataSimulatorConfig:
    latency_offset_secs: int = 30
    window_secs: int = 10


@dataclass(slots=True)
class MarketAlignerConfig:
    stale_threshold_ms: float = 15_000.0


@dataclass(slots=True)
class PredictorConfig:
    clip_epsilon: float = 1e-6
    score_scale: float = 0.35


@dataclass(slots=True)
class CommanderConfig:
    entry_threshold: float = 0.03
    min_depth_usd: float = 500.0
    s_tier_only: bool = True
    default_notional_usd: float = 100.0


@dataclass(slots=True)
class ExecutionConfig:
    base_latency_ms: float = 500.0
    jitter_ms: float = 100.0
    latency_seed: int = 42
    stale_threshold_ms: float = 15_000.0


@dataclass(slots=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    initial_cash: float = 10_000.0
    position_size: float = 100.0
    simulator: DataSimulatorConfig = field(default_factory=DataSimulatorConfig)
    aligner: MarketAlignerConfig = field(default_factory=MarketAlignerConfig)
    predictor: PredictorConfig = field(default_factory=PredictorConfig)
    commander: CommanderConfig = field(default_factory=CommanderConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
