import pandas as pd

class DataHandler:
    """
    负责数据的加载、验证和标准化。
    """
    REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

    @staticmethod
    def validate(df: pd.DataFrame) -> pd.DataFrame:
        """
        验证 DataFrame 是否符合 Bar/Series 约定。
        1. 必须包含 datetime index
        2. 必须包含 open, high, low, close, volume 列
        3. 列名统一转换为小写
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            # 尝试将 index 转换为 datetime
            try:
                df.index = pd.to_datetime(df.index)
            except Exception as e:
                raise ValueError("DataFrame index must be DatetimeIndex or convertible to DatetimeIndex") from e

        # 统一列名为小写
        df.columns = [c.lower() for c in df.columns]

        # 检查必需列
        missing_columns = [col for col in DataHandler.REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # 确保数据类型为数值型
        for col in DataHandler.REQUIRED_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 删除任何包含 NaN 的行 (可选，视策略而定，这里暂时保留原始行为，由后续步骤处理)
        # df.dropna(subset=DataHandler.REQUIRED_COLUMNS, inplace=True)

        return df

    @staticmethod
    def load_csv(file_path: str) -> pd.DataFrame:
        """从 CSV 加载并验证"""
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return DataHandler.validate(df)

    @staticmethod
    def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """
        Resample OHLCV data to a higher timeframe.
        rule: "4H", "1D", etc.
        """
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        # Only aggregate columns that exist
        current_agg = {k: v for k, v in agg_dict.items() if k in df.columns}
        
        # Resample
        # closed='right', label='right' ensures that the bar labeled '04:00' contains data ending at '04:00'
        # This aligns with the concept that the timestamp represents the CLOSE time.
        resampled = df.resample(rule, closed='right', label='right').agg(current_agg)
        
        # Drop NaNs created by resampling (e.g. gaps)
        resampled.dropna(inplace=True)
        
        return resampled

    @staticmethod
    def analyze_quality(df: pd.DataFrame, symbol: str = "Unknown") -> dict:
        """
        Analyze data quality: gaps, duplicates, spikes.
        """
        report = {
            "symbol": symbol,
            "total_rows": len(df),
            "start_date": str(df.index.min()),
            "end_date": str(df.index.max()),
            "duplicates": df.index.duplicated().sum(),
            "missing_values": df.isnull().sum().to_dict(),
            "gaps": 0,
            "spikes": 0
        }

        # Check for gaps (assuming regular frequency if possible)
        # Calculate time diffs
        if len(df) > 1:
            diffs = df.index.to_series().diff().dropna()
            # Infer frequency: median diff
            freq = diffs.median()
            # Gaps: diff > 1.5 * freq
            gaps = diffs[diffs > 1.5 * freq]
            report["gaps"] = len(gaps)
            report["expected_freq"] = str(freq)
            
            # Check for price spikes (> 20% change in one bar)
            # pct_change
            returns = df['close'].pct_change().abs()
            spikes = returns[returns > 0.20]
            report["spikes"] = len(spikes)
            
        return report

    @staticmethod
    def generate_quality_report(data_map: dict, output_path: str = None) -> dict:
        """
        Generate comprehensive quality report for multiple symbols.
        """
        full_report = {}
        for symbol, df in data_map.items():
            full_report[symbol] = DataHandler.analyze_quality(df, symbol)
            
        if output_path:
            import json
            try:
                with open(output_path, 'w') as f:
                    json.dump(full_report, f, indent=4, default=str)
                print(f"Data quality report saved to {output_path}")
            except Exception as e:
                print(f"Failed to save data quality report: {e}")
                
        return full_report
