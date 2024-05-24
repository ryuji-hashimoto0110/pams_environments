import datetime
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.pyplot import Axes, Figure
import numpy as np
from numpy import ndarray
import pandas as pd
from pandas import DataFrame
from pandas import Timestamp
from pathlib import Path
import random
from rich.console import Console
from rich.table import Table
from scipy.stats import kurtosis, kurtosistest
from tqdm import tqdm
from typing import Optional
import warnings

freq_ohlcv_size_dict: dict[str, int] = {
    "1s": 18002,
    "30s": 602,
    "1min": 302,
    "5min": 62,
    "15min": 22
}

class StylizedFactsChecker:
    """StylizedFactsChecker class.

    StylizedFactsChecker has 2 roles.
        1. preprocess artificial / real datas to compare them in equal ways.
        2. check whether the data satisfy various stylized facts.
    """
    def __init__(
        self,
        seed: int = 42,
        ohlcv_dfs_path: Optional[Path] = None,
        tick_dfs_path: Optional[Path] = None,
        resample_rule: str = "1min",
        is_real: bool = True,
        ohlcv_dfs_save_path: Optional[Path] = None,
        choose_full_size_df: bool = True,
        specific_name: Optional[str] = None,
        figs_save_path: Optional[Path] = None,
        session1_end_time_str: Optional[str] = None,
        session2_start_time_str: Optional[str] = None,
        transactions_folder_path: Optional[Path] = None,
        session1_transactions_file_name: Optional[str] = None,
        session2_transactions_file_name: Optional[str] = None
    ) -> None:
        """initialization.

        load dataframes.

        Args:
            ohlcv_dfs_path (Optional[Path]): path in which ohlcv csv datas are saved. Default to None.
                ohlcv data consists of 5 columns: open, high, low, close, volume.
            tick_dfs_path (Optional[Path]): path in which tick csv datas are saved. Default to None.
            is_real (bool): whether df is real_data
            ohlcv_dfs_save_path (Optional[Path]):
            choose_full_size_df
            specific_name (Optional[str]): the specific name in csv file name. Files that contain specific_name
                are collected if this argument is specified by _read_csvs.
            figs_save_path (Optional[Path]): path to save figures.
            session1_end_time_str (Optional[str]):
            session2_start_time_str (Optional[str]):
        """
        self.prng = random.Random(seed)
        self.is_real: bool = is_real
        self.resample_rule: str = resample_rule
        self.ohlcv_dfs: list[DataFrame] = []
        self.ohlcv_csv_names: list[str] = []
        self.tick_dfs: list[DataFrame] = []
        self.specific_name: Optional[str] = specific_name
        self.session1_end_time: Optional[Timestamp] = None
        if session1_end_time_str is not None:
            self.session1_end_time = pd.to_datetime(session1_end_time_str).time()
        self.session2_start_time: Optional[Timestamp] = None
        if session2_start_time_str is not None:
            self.session2_start_time = pd.to_datetime(session2_start_time_str).time()
        if ohlcv_dfs_save_path is not None:
            if not ohlcv_dfs_save_path.exists():
                ohlcv_dfs_save_path.mkdir(parents=True)
        self.transactions_folder_path: Optional[Path] = transactions_folder_path
        self.session1_transactions_file_name: Optional[str] = session1_transactions_file_name
        self.session2_transactions_file_name: Optional[str] = session2_transactions_file_name
        if tick_dfs_path is not None:
            print("read tick dfs")
            self._read_tick_dfs(tick_dfs_path)
            if ohlcv_dfs_path is None:
                print("read tick dfs, resampling")
                self.ohlcv_dfs, self.ohlcv_csv_names = self._read_csvs(
                    tick_dfs_path,
                    need_resample=True,
                    choose_full_size_df=choose_full_size_df
                )
        if ohlcv_dfs_path is not None:
            print("read OHLCV dfs")
            self._read_ohlcv_dfs(ohlcv_dfs_path, choose_full_size_df)
        print("preprocess dfs")
        for i, df in tqdm(enumerate(self.ohlcv_dfs)):
            self.preprocess_ohlcv_df(df)
            csv_name: str = self.ohlcv_csv_names[i]
            save_path: Path = ohlcv_dfs_save_path / csv_name
            df.to_csv(str(save_path))
        if not figs_save_path.exists():
            figs_save_path.mkdir(parents=True)
        self.figs_save_path: Optional[Path] = figs_save_path
        self.return_arr: Optional[ndarray] = None
        self.abs_hill_index: Optional[float] = None

    def _read_csvs(
        self,
        csvs_path: Path,
        need_resample: bool,
        choose_full_size_df: bool = False
    ) -> tuple[list[DataFrame], list[str]]:
        """read all csv files in given folder path.

        Args:
            csvs_path (Path): folder path to be searched for target csvs.
            need_resample (bool): whether resampling is needed. If True, all target csvs must be tick data.
        """
        dfs: list[DataFrame] = []
        csv_names: list[str] = []
        for csv_path in tqdm(sorted(csvs_path.rglob("*.csv"))):
            store_df: bool = True
            csv_name: str = csv_path.name
            if self.specific_name is not None:
                if self.specific_name not in csv_name:
                    continue
            df: DataFrame = pd.read_csv(csv_path, index_col=0)
            if need_resample:
                df = self._resample(df)
                if len(df) < freq_ohlcv_size_dict[self.resample_rule] and choose_full_size_df:
                    store_df = False
                else:
                    store_df = True
            if store_df:
                csv_names.append(csv_name)
                dfs.append(df)
        return dfs, csv_names

    def _resample(self, df: DataFrame) -> DataFrame:
        """resample tick data to OHLCV data.

        Args:
            df (DataFrame): dataframe of tick data. df must have at least "market_price", "num_events" columns.
        """
        assert "market_price" in df.columns
        assert "event_volume" in df.columns
        if self.is_real:
            return self._resample_real(df)
        else:
            return self._resample_art(df)

    def _resample_real(self, df: DataFrame) -> DataFrame:
        df.index = pd.to_datetime(df.index, format="%H:%M:%S.%f") #09:00:00.357000
        resampled_df: DataFrame = df["market_price"].resample(
            rule=self.resample_rule, closed="left", label="left"
        ).ohlc()
        resampled_df["volume"] = df["event_volume"].resample(
            rule=self.resample_rule, closed="left", label="left"
        ).apply("sum")
        resampled_df["num_events"] = df["event_volume"].resample(
            rule=self.resample_rule, closed="left", label="left"
        ).count()
        resampled_df.index = resampled_df.index.time
        resampled_df["close"] = resampled_df["close"].ffill()
        resampled_df = resampled_df[
            (resampled_df.index <= self.session1_end_time) | \
            (self.session2_start_time <= resampled_df.index)
        ]
        return resampled_df

    def _resample_art(self, df: DataFrame) -> DataFrame:
        assert "session_id" in df.columns
        session1_df: DataFrame = df[df["session_id"] == 1]
        session1_resampled_df: DataFrame = self._resample_art_per_session(
            session1_df, self.session1_transactions_file_name
        )
        if self.session1_end_time is None:
            self.session1_end_time = pd.to_datetime(
                session1_resampled_df.index[-1]
            ).time()
        session2_df: DataFrame = df[df["session_id"] == 2]
        session2_resampled_df: DataFrame = self._resample_art_per_session(
            session2_df, self.session2_transactions_file_name
        )
        if self.session2_start_time is None:
            self.session2_start_time = pd.to_datetime(
                session2_resampled_df.index[0]
            ).time()
        resampled_df: DataFrame = pd.concat(
            [session1_resampled_df, session2_resampled_df], axis=0
        )
        resampled_df.index = pd.to_datetime(resampled_df.index, format="%H:%M:%S")
        resampled_df.index = resampled_df.index.time
        resampled_df["close"] = resampled_df["close"].ffill()
        return resampled_df

    def _resample_art_per_session(
        self,
        df: DataFrame,
        transactions_file_name: str
    ) -> DataFrame:
        assert self.transactions_folder_path is not None
        assert transactions_file_name
        transactions_file_path: Path = self.transactions_folder_path / transactions_file_name
        cumsum_scaled_transactions_df: DataFrame = pd.read_csv(
            str(transactions_file_path), index_col=0
        )
        indexes = cumsum_scaled_transactions_df.index
        cumsum_scaled_transactions_arr: ndarray = cumsum_scaled_transactions_df[
            self.prng.choice(cumsum_scaled_transactions_df.columns)
        ].values
        cumsum_transactions_arr: ndarray = len(df) * cumsum_scaled_transactions_arr
        cumsum_transactions: list[int] = list(cumsum_transactions_arr.astype(np.uint8))
        opens: list[Optional[float | int]] = []
        highes: list[Optional[float | int]] = []
        lowes: list[Optional[float | int]] = []
        closes: list[float | int] = []
        volumes: list[int] = []
        num_events: list[int] = []
        num_pre_transactions: int = 0
        for num_cur_transactions in cumsum_transactions:
            cur_df: DataFrame = df.iloc[num_pre_transactions:num_cur_transactions,:]
            if 0 < len(cur_df):
                opens.append(cur_df["event_price (avg)"].iloc[0])
                highes.append(cur_df["event_price (avg)"].max())
                lowes.append(cur_df["event_price (avg)"].min())
                closes.append(cur_df["event_price (avg)"].iloc[-1])
                volumes.append(cur_df["event_volume"].sum())
                num_events.append(len(cur_df))
            else:
                opens.append(None)
                highes.append(None)
                lowes.append(None)
                closes.append(None)
                volumes.append(0)
                num_events.append(0)
            num_pre_transactions = num_cur_transactions
        session_resampled_df: DataFrame = pd.DataFrame(
            data={
                "open": opens, "high": highes, "low": lowes, "close": closes,
                "volume": volumes, "num_events": num_events
            },
            index=indexes
        )
        session_resampled_df["close"] = session_resampled_df["close"].ffill()
        return session_resampled_df

    def _read_tick_dfs(self, tick_dfs_path: Path) -> None:
        self.tick_dfs, _ = self._read_csvs(
            tick_dfs_path,
            need_resample=False
        )

    def _read_ohlcv_dfs(self, ohlcv_dfs_path: Path, choose_full_size_df: bool) -> None:
        self.ohlcv_dfs, self.ohlcv_csv_names = self._read_csvs(
            ohlcv_dfs_path,
            need_resample=False,
            choose_full_size_df=choose_full_size_df
        )

    def preprocess_ohlcv_df(
        self,
        df: DataFrame,
    ) -> None:
        """preprocess OHLCV dataframe.

        This method preprocess OHLCV dataframe with following procedure.

        1. lowercase column names.
        2. create scaled num_events and volume column.
        3. assign session ID.

        Args:
            df (DataFrame): dataframe of OHLCV data.

        Returns:
            DataFrame: _description_
        """
        df.columns = df.columns.str.lower()
        if not "scaled_volume" in df.columns:
            df["scaled_volume"] = df["volume"] / df["volume"].sum()
        if not "scaled_num_events" in df.columns:
            df["scaled_num_events"] = df["num_events"] / df["num_events"].sum()
        if self.session1_end_time is not None:
            if not "session1_scaled_volume" in df.columns:
                df["session1_scaled_volume"] = np.zeros(len(df))
                df.loc[
                    df.index <= self.session1_end_time, ["session1_scaled_volume"]
                ] = df["scaled_volume"][df.index <= self.session1_end_time]
                df["session1_scaled_volume"] = df["session1_scaled_volume"] / df["session1_scaled_volume"].sum()
            if not "session1_scaled_num_events" in df.columns:
                df["session1_scaled_num_events"] = np.zeros(len(df))
                df.loc[
                    df.index <= self.session1_end_time, ["session1_scaled_num_events"]
                ] = df["scaled_num_events"][df.index <= self.session1_end_time]
                df["session1_scaled_num_events"] = df["session1_scaled_num_events"] / df["session1_scaled_num_events"].sum()
        if self.session2_start_time is not None:
            if not "session2_scaled_volume" in df.columns:
                df["session2_scaled_volume"] = np.zeros(len(df))
                df.loc[
                    self.session2_start_time <= df.index, ["session2_scaled_volume"]
                ] = df["scaled_volume"][self.session2_start_time <= df.index]
                df["session2_scaled_volume"] = df["session2_scaled_volume"] / df["session2_scaled_volume"].sum()
            if not "session2_scaled_num_events" in df.columns:
                df["session2_scaled_num_events"] = np.zeros(len(df))
                df.loc[
                    self.session2_start_time <= df.index, ["session2_scaled_num_events"]
                ] = df["scaled_num_events"][self.session2_start_time <= df.index]
                df["session2_scaled_num_events"] = df["session2_scaled_num_events"] / df["session2_scaled_num_events"].sum()
        return df

    def _is_stacking_possible(
        self,
        dfs: list[DataFrame],
        colname: str
    ) -> bool:
        """check if it is possible to stack given column in dfs into ndarray.

        Return True if all follwing conditions hold true.
            - column named colname exists in all dataframes.
            - length of all dataframes are the same.
            - number of NaN in df[colname] of all dataframes are the same.

        Args:
            dfs (list[DataFrame]): list whose elements are dataframe. Ex: self.ohlcv_dfs
            colname (str): column name to check if stacking is possible.
        """
        for df in dfs:
            if colname not in df.columns:
                return False
        if [len(df) for df in dfs].count(len(dfs[0])) != len(dfs):
            return False
        if [df[colname].isnull().sum() for df in dfs].count(dfs[0][colname].isnull().sum()) != len(dfs):
            return False
        return True

    def _stack_dfs(
        self,
        dfs: list[DataFrame],
        colname: str
    ) -> ndarray:
        """stack specified column of all dataframes.

        Args:
            dfs (list[DataFrame]): list whose elements are dataframe. Ex: self.ohlcv_dfs
            colname (str): column name to stack.

        Returns:
            stacked_arr (ndarray): array whose shape is (len(dfs), len(dfs[0]))
        """
        assert self._is_stacking_possible(dfs, colname)
        col_arrs: list[ndarray] = [df[colname].dropna().values for df in dfs]
        stacked_arr: ndarray = np.stack(col_arrs, axis=0)
        assert stacked_arr.shape == (len(col_arrs), len(col_arrs[0]))
        return stacked_arr

    def _calc_return_arr_from_df(
        self,
        ohlcv_df: DataFrame,
        colname: str
    ) -> ndarray:
        """convert price time series to return time series from 1 dataframe.
        """
        price_arr: ndarray = ohlcv_df[colname].dropna().values
        assert np.sum((price_arr <= 0)) == 0
        return_arr: ndarray = np.log(
            price_arr[1:] / price_arr[:-1] + 1e-10
        )[np.newaxis,:]
        return return_arr

    def _calc_return_arr_from_dfs(
        self,
        ohlcv_dfs: list[DataFrame],
        colname: str,
        is_abs: bool = False
    ) -> ndarray:
        """convert price time series to return time series from dataframes list.
        """
        price_arr: ndarray = self._stack_dfs(ohlcv_dfs, colname)
        assert np.sum((price_arr <= 0)) == 0
        return_arr: ndarray = np.log(
            price_arr[:,1:] / price_arr[:,:-1] + 1e-10
        )
        if is_abs:
            return_arr: ndarray = np.abs(return_arr)
        return return_arr

    def _calc_cumsum_transactions_from_df(
        self,
        ohlcv_df: DataFrame,
        colname: str
    ) -> ndarray:
        """convert scaled number of transactions time series to
        cumulative scaled number of transactions time series from 1 dataframe.
        """
        scaled_transactions: ndarray = ohlcv_df[colname].dropna().values
        cumsum_scaled_transactions = np.cumsum(scaled_transactions)[np.newaxis,:]
        return cumsum_scaled_transactions

    def _calc_cumsum_transactions_from_dfs(
        self,
        ohlcv_dfs: list[DataFrame],
        colname: str
    ) -> ndarray:
        """convert scaled number of transactions time series to
        cumulative scaled number of transactions time series from dataframes list.
        """
        scaled_transactions: ndarray = self._stack_dfs(ohlcv_dfs, colname)
        cumsum_scaled_transactions = np.cumsum(scaled_transactions, axis=1)
        return cumsum_scaled_transactions

    def check_kurtosis(self) -> tuple[ndarray, ndarray]:
        """check the kurtosis of given price time series.

        Kurtosis of stock returns is generally said to be greater than 3
        (0 if calculated according to the terms with fisher).
        This method calculate kurtosises of each time series data and test if
        each kurtosis is greater than that of gaussian distribution.

        References:
            - Mandelbrot, B. (1967). The Variation of Certain Speculative Prices,
            Journal of Business, 36 (3), 394-419. http://www.jstor.org/stable/2350970
            - Fama, E. (1965). The Behaviour of Stock Market Prices. Journal of Business,
            Journal of Business, 38 (1), 34-105. https://www.jstor.org/stable/2350752

        Returns:
            kurtosis_arr (ndarray): kurtosises. (number of data,1)
            pvalues_arr (ndarray): p-values. (number of data,1)
        """
        if self._is_stacking_possible(self.ohlcv_dfs, "close"):
            if self.return_arr is not None:
                kurtosis_arr, pvalue_arr = self._calc_kurtosis(self.return_arr)
            else:
                self.return_arr: ndarray = self._calc_return_arr_from_dfs(
                    self.ohlcv_dfs, "close"
                )
                kurtosis_arr, pvalue_arr = self._calc_kurtosis(self.return_arr)
        else:
            warnings.warn(
                "Could not stack dataframe. Maybe the lengths of dataframes differ. Following procedure may takes time..."
            )
            kurtosises: list[float] = []
            pvalues: list[float] = []
            for ohlcv_df in self.ohlcv_dfs:
                return_arr: ndarray = self._calc_return_arr_from_df(ohlcv_df, "close")
                kurtosis, pvalue = self._calc_kurtosis(return_arr)
                kurtosises.append(kurtosis.item())
                pvalues.append(pvalue.item())
            kurtosis_arr: ndarray = np.array(kurtosises)[:,np.newaxis]
            pvalue_arr: ndarray = np.array(pvalues)[:,np.newaxis]
        return kurtosis_arr, pvalue_arr

    def _calc_kurtosis(
        self,
        return_arr: ndarray,
        is_fisher: bool = True
    ) -> tuple[ndarray, ndarray]:
        """calculate kurtosis of each time series array.

        Args:
            return_arr (ndarray): return array whose shape is
                (number of data, length of time series).
            is_fisher (bool): Defaults to True.

        Returns:
            kurtosis_arr (ndarray): kurtosises. (number of data, 1)
            pvalues_arr (ndarray): p-values. (number of data, 1)
        """
        if len(return_arr.shape) != 2:
            raise ValueError(
                "The shape of return_arr must be (number of data, length of time series)."
            )
        kurtosis_arr: ndarray = kurtosis(
            return_arr, axis=1, fisher=is_fisher, keepdims=True
        )
        pvalue_arr: ndarray = kurtosistest(
            return_arr, axis=1, alternative="greater"
        )[1][:,np.newaxis]
        return kurtosis_arr, pvalue_arr

    def check_hill_index(
        self,
        cut_off_th: float = 0.05
    ) -> tuple[ndarray, ndarray, ndarray]:
        """check Hill-tail index of given price time series.

        The stock return distribution is generally said to be fat-tail.
        According to some empirical researches, the tail index is normally around or below 3
        in real markets (universal cubic law).
        Also, the skewness of the returns is negative. In other words,
        tail due to negative returns is fatter than that due to positive returns.

        Note: Hill Index assumes non-negative values in tail area. Therefore, to calculate
        both left and right tail indices, the mean of return distribution must be in near 0.

        References:
            - Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution,
            Annals of Statistics 3 (5), 1163-1173. https://doi.org/10.1214/aos/1176343247
            - Lux, T. (2001). The limiting extremal behaviour of speculative returns:
            an analysis of intra-daily data from the Frankfurt Stock Exchange,
            Applied Financial Economics, 11, 299-315. https://doi.org/10.1080/096031001300138708
            - Gabaix, X., Gopikrishnan, P., Plerou, V., Stanley, H. E. (2003).
            A theory of power-low distributions in financial market fluctuations,
            Nature 423, 267-270. http://dx.doi.org/10.1038/nature01624

        Args:
            cut_off_th (float): threshold to cut-off samples inside tail of the distributions.
                Default to 0.05.

        Returns:
            left_tail_arr (ndarray): tail indices of left side of samples.
            right_tail_arr (ndarray): tail indices of right side of samples.
        """
        assert 0 < cut_off_th and cut_off_th < 1
        if self._is_stacking_possible(self.ohlcv_dfs, "close"):
            if self.return_arr is None:
                self.return_arr: ndarray = self._calc_return_arr_from_dfs(
                    self.ohlcv_dfs, "close"
                )
            return_arr_flatten: ndarray = self.return_arr.flatten()[np.newaxis,:]
            left_tail_arr, right_tail_arr, abs_tail_arr = self._calc_both_sides_hill_indices(
                return_arr_flatten, cut_off_th
            )
        else:
            warnings.warn(
                "Could not stack dataframe. Maybe the lengths of dataframes differ. Following procedure may takes time..."
            )
            return_arr_flatten: ndarray = np.array([], dtype=np.float32)
            for ohlcv_df in self.ohlcv_dfs:
                return_arr_flatten: ndarray = np.concatenate(
                    [return_arr_flatten, self._calc_return_arr_from_df(ohlcv_df, "close").flatten()]
                )
            return_arr_flatten = return_arr_flatten[np.newaxis,:]
            left_tail_arr, right_tail_arr, abs_tail_arr = self._calc_both_sides_hill_indices(
                return_arr_flatten, cut_off_th
            )
        return left_tail_arr, right_tail_arr, abs_tail_arr

    def _calc_hill_indices(
        self,
        sorted_return_arr: ndarray,
        cut_off_th: float = 0.05
    ) -> ndarray:
        """calculate right side Hill tail indices of ascendinglly sorted return array.

        Args:
            sorted_return_arr (ndarray): return array whose shape is
                (number of data, length of time series).
                This array must be ascendinglly sorted.
            cut_off_th (float): threshold to cut-off samples inside tail of the distributions.
                Default to 0.05.

        Returns:
            tail_arr (ndarray): tail indices. (number of data, 1)
        """
        assert len(sorted_return_arr.shape) == 2
        if np.sum(sorted_return_arr != np.sort(sorted_return_arr, axis=1)) != 0:
            raise ValueError(
                "sorted_return_arr must be ascendinglly sorted"
            )
        cut_sorted_return_arr: ndarray = sorted_return_arr[
            :,int(np.floor(sorted_return_arr.shape[1] * (1-cut_off_th))):
        ]
        if np.sum(cut_sorted_return_arr <= 0) != 0:
            raise ValueError(
                "Non positive elements found in tail area of sorted_return_arr. Maybe you should reduce cut_off_th."
            )
        k: int = cut_sorted_return_arr.shape[1]
        tail_arr: ndarray = 1 / k * np.sum(
            np.log(cut_sorted_return_arr / cut_sorted_return_arr[:,0][:,np.newaxis]),
            axis=1
        )[:,np.newaxis]
        tail_arr: ndarray = 1 / tail_arr
        return tail_arr

    def _calc_both_sides_hill_indices(
        self,
        return_arr: ndarray,
        cut_off_th: float = 0.05
    ) -> tuple[ndarray, ndarray]:
        """_summary_

        Args:
            return_arr (ndarray): _description_
            cut_off_th (float, optional): _description_. Defaults to 0.05.

        Returns:
            left_tail_arr (ndarray): _description_
            right_tail_arr (ndarray): _description_
        """
        sorted_return_arr: ndarray = np.sort(return_arr, axis=1)
        right_tail_arr: ndarray = self._calc_hill_indices(
            sorted_return_arr, cut_off_th
        )
        minus_return_arr: ndarray = - 1 * return_arr
        sorted_minus_return_arr: ndarray = np.sort(minus_return_arr, axis=1)
        left_tail_arr: ndarray = self._calc_hill_indices(
            sorted_minus_return_arr, cut_off_th
        )
        sorted_abs_return_arr: ndarray = np.sort(
            np.abs(return_arr), axis=1
        )
        abs_tail_arr: ndarray = self._calc_hill_indices(
            sorted_abs_return_arr, cut_off_th
        )
        return left_tail_arr, right_tail_arr, abs_tail_arr

    def check_autocorrelation(self, lags: list[int]) -> dict[int, ndarray]:
        """_summary_

        Args:
            lags (list[int]): _description_

        Returns:
        """
        if self._is_stacking_possible(self.ohlcv_dfs, "close"):
            if self.return_arr is None:
                self.return_arr: ndarray = self._calc_return_arr_from_dfs(
                    self.ohlcv_dfs, "close"
                )
            acorr_dic: dict[int, ndarray] = self._calc_autocorrelation(
                np.abs(self.return_arr), lags
            )
        else:
            warnings.warn(
                "Could not stack dataframe. Maybe the lengths of dataframes differ. Following procedure may takes time..."
            )
            acorr_l_dic: dict[int, list[float]] = {lag: [] for lag in lags}
            for ohlcv_df in self.ohlcv_dfs:
                return_arr: ndarray = self._calc_return_arr_from_df(ohlcv_df, "close")
                acorr_dic_: dict[int, float] = self._calc_autocorrelation(
                    np.abs(return_arr), lags
                )
                for lag in lags:
                    acorr_l_dic[lag].append(acorr_dic_[lag].item())
            acorr_dic: dict[int, ndarray] = {}
            for lag, acorrs in acorr_l_dic.items():
                acorr_dic[lag] = np.array(acorrs)[:,np.newaxis]
        return acorr_dic

    def _calc_autocorrelation(
        self,
        abs_return_arr: ndarray,
        lags: list[int]
    ) -> dict[int, ndarray]:
        """_summary_

        Args:
            return_arr (ndarray): _description_
            lags (list[int]): _description_

        Returns:
            dict[int, ndarray]: _description_
        """
        acorr_dic: list[int, ndarray] = {}
        for lag in lags:
            abs_mean: ndarray = np.mean(abs_return_arr, axis=1, keepdims=True)
            acov: ndarray = np.mean(
                (abs_return_arr[:,lag:]-abs_mean)*(abs_return_arr[:,:-lag]-abs_mean),
                axis=1, keepdims=True
            )
            var: ndarray = np.var(abs_return_arr, axis=1, keepdims=True)
            acorr_dic[lag] = acov / (var + 1e-10)
        return acorr_dic

    def check_volume_volatility_correlation(self) -> ndarray:
        if self._is_stacking_possible(self.ohlcv_dfs, "close"):
            volume_arr: ndarray = self._stack_dfs(
                self.ohlcv_dfs, "volume"
            )
            volume_arr = volume_arr[:,1:]
            if self.return_arr is None:
                self.return_arr: ndarray = self._calc_return_arr_from_dfs(
                    self.ohlcv_dfs, "close"
                )
            corr_arr: ndarray = self._calc_volume_volatility_correlation(
                np.abs(self.return_arr), volume_arr
            )
        else:
            warnings.warn(
                "Could not stack dataframe. Maybe the lengths of dataframes differ. Following procedure may takes time..."
            )
            corrs: list[float] = []
            for ohlcv_df in self.ohlcv_dfs:
                return_arr: ndarray = self._calc_return_arr_from_df(ohlcv_df, "close")
                volume_arr: ndarray = ohlcv_df["volume"].values[np.newaxis,1:]
                corrs.append(
                    self._calc_volume_volatility_correlation(
                        np.abs(return_arr), volume_arr
                    ).item()
                )
            corr_arr: ndarray = np.array(corrs)[np.newaxis,:]
        return corr_arr

    def _calc_volume_volatility_correlation(
        self,
        abs_return_arr: ndarray,
        volume_arr: ndarray
    ) -> ndarray:
        """_summary_

        Args:
            abs_return_arr (ndarray): _description_ (number of data, length of time series).
            volume_arr (ndarray): _description_ (number of data, length of time series).

        Returns:
            ndarray: _description_ (number of data, 1).
        """
        abs_return_mean: ndarray = np.mean(
            abs_return_arr, axis=1, keepdims=True
        )
        volume_mean: ndarray = np.mean(
            volume_arr, axis=1, keepdims=True
        )
        abs_retrurn_std: ndarray = np.std(
            abs_return_arr, axis=1, keepdims=True
        )
        volume_std: ndarray = np.std(
            volume_arr, axis=1, keepdims=True
        )
        volume_volatility_correlation: ndarray = np.mean(
            (abs_return_arr - abs_return_mean) * (volume_arr - volume_mean),
            axis=1, keepdims=True
        ) / (
            abs_retrurn_std * volume_std + 1e-10
        )
        return volume_volatility_correlation

    def check_stylized_facts(
        self,
        save_path: Path,
        print_results: bool = True
    ) -> None:
        if 0 < len(self.ohlcv_dfs):
            kurtosis_arr, p_values = self.check_kurtosis()
            left_tail_arr, right_tail_arr, abs_tail_arr = self.check_hill_index()
            left_tail_arr = np.repeat(left_tail_arr, repeats=kurtosis_arr.shape[0])
            right_tail_arr = np.repeat(right_tail_arr, repeats=kurtosis_arr.shape[0])
            abs_tail_arr = np.repeat(abs_tail_arr, repeats=kurtosis_arr.shape[0])
            volume_volatility_correlation = self.check_volume_volatility_correlation()
            acorr_dic: dict[int, ndarray] = self.check_autocorrelation(
                [lag for lag in range(1,31)]
            )
            data_dic: dict[str, ndarray]= {
                "kurtosis": kurtosis_arr.flatten(),
                "kurtosis_p": p_values.flatten(),
                "tail (left)": left_tail_arr.flatten(),
                "tail (right)": right_tail_arr.flatten(),
                "tail (abs)": abs_tail_arr.flatten(),
                "vv_corr": volume_volatility_correlation.flatten()
            }
            for lag, acorr in acorr_dic.items():
                data_dic[f"acorr lag{lag}"] = acorr.flatten()
            stylized_facts_df: DataFrame = pd.DataFrame(data_dic)
            if print_results:
                self.print_results(stylized_facts_df)
            stylized_facts_df.to_csv(str(save_path))

    def print_results(
        self,
        stylized_facts_df: DataFrame
    ) -> None:
        table: Table = Table(title="results of stylized facts")
        table.add_column("Indicator", justify="right", style="cyan")
        table.add_column("Mean", justify="left", style="magenta")
        table.add_column("Std", justify="left", style="green")
        described_df: DataFrame = stylized_facts_df.describe()
        for column_name in stylized_facts_df.columns:
            table.add_row(
                column_name,
                str(described_df.loc["mean"][column_name]),
                str(described_df.loc["std"][column_name])
            )
        console = Console()
        console.print(table)

    def plot_ccdf(
        self,
        ax: Optional[Axes] = None,
        label: str = "CCDF",
        color: str = "black",
        img_save_name: Optional[str] = None,
        draw_idx: Optional[int] = None
    ) -> None:
        """draw CCDF of return distribution by log-log scale.

        Complementary cumulative distribution function (CCDF) is defined as P[x<X], namely
        defined as the probability that stochastic variable X is greater than a certain
        threshold x.
        CCDF is used to see the tail of samples that seems to be fitted by power law. Here,
        using CCDF, one can check visually that return distribution is fat-tailed.

        Args:
            ax (Optional[Axes]): ax to draw figure. default to None.
            label: label
            color: color
            save_name (Optional[str]): file name to save figure. Default to None.
            draw_idx (Optional[int]): If draw_idx is specified, price data of
                self.ohlcv_dfs[draw_idx] is only chosen to draw figure. Otherwise, all data
                are concatted and used to draw. Defaults to None.
        """
        if draw_idx is None:
            if self._is_stacking_possible(self.ohlcv_dfs, "close"):
                if self.return_arr is None:
                    self.return_arr: ndarray = self._calc_return_arr_from_dfs(
                        self.ohlcv_dfs, "close"
                    )
                return_arr: ndarray = self.return_arr.flatten()
            else:
                warnings.warn(
                    "Could not stack dataframe. Maybe the lengths of dataframes differ." + \
                    "Following procedure may takes time..."
                )
                return_arrs: list[ndarray] = []
                for ohlcv_df in self.ohlcv_dfs:
                    return_arrs.append(
                        self._calc_return_arr_from_df(ohlcv_df, "close").flatten()
                    )
                return_arr: ndarray = np.concatenate(return_arrs)
        else:
            return_arr: ndarray = self._calc_return_arr_from_df(
                self.ohlcv_dfs[draw_idx], "close"
            ).flatten()
        assert len(return_arr.shape) == 1
        sorted_abs_return_arr: ndarray = np.sort(np.abs(return_arr))
        ccdf: ndarray = 1 - (
            1 + np.arange(len(sorted_abs_return_arr))
        ) / len(sorted_abs_return_arr)
        if ax is None:
            fig: Figure = plt.figure(figsize=(10,6))
            ax: Axes = fig.add_subplot(1,1,1)
        ax.plot(sorted_abs_return_arr, ccdf, color=color, label=label)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("return")
        ax.set_ylabel("CCDF")
        ax.set_title("Complementary Cumulative Distribution Function (CCDF) of absolute price returns")
        ax.set_xlim([0.0001, 0.1])
        if img_save_name is not None:
            if self.figs_save_path is None:
                raise ValueError(
                    "specify directory: self.figs_save_path"
                )
            save_path: Path = self.figs_save_path / img_save_name
            plt.savefig(str(save_path))

    def calc_mean_cumulative_transactions(
        self,
        transactions_save_path: Optional[Path] = None,
        return_mean: bool = True,
        session_name: Optional[int] = None
    ) -> Optional[ndarray]:
        assert self._is_stacking_possible(self.ohlcv_dfs, "scaled_num_events")
        if session_name is None:
            cumsum_scaled_transactions_arr: ndarray = self._calc_cumsum_transactions_from_dfs(
                self.ohlcv_dfs, colname="scaled_num_events"
            )
            indexes = self.ohlcv_dfs[0].index
        elif session_name == "session1":
            cumsum_scaled_transactions_arr: ndarray = self._calc_cumsum_transactions_from_dfs(
                self.ohlcv_dfs, colname="session1_scaled_num_events"
            )
            cumsum_scaled_transactions_arr = cumsum_scaled_transactions_arr[
                :, (self.ohlcv_dfs[0].index <= self.session1_end_time)
            ]
            indexes = self.ohlcv_dfs[0][self.ohlcv_dfs[0].index <= self.session1_end_time].index
        elif session_name == "session2":
            cumsum_scaled_transactions_arr: ndarray = self._calc_cumsum_transactions_from_dfs(
                self.ohlcv_dfs, colname="session2_scaled_num_events"
            )
            cumsum_scaled_transactions_arr = cumsum_scaled_transactions_arr[
                :, (self.session2_start_time <= self.ohlcv_dfs[0].index)
            ]
            indexes = self.ohlcv_dfs[0][self.session2_start_time <= self.ohlcv_dfs[0].index].index
        else:
            raise ValueError(
                f"unknown session_name: {session_name}"
            )
        cumsum_scaled_transactions_arr = cumsum_scaled_transactions_arr.T
        cumsum_scaled_transactions_df: DataFrame = pd.DataFrame(
            data=cumsum_scaled_transactions_arr, index=indexes
        )
        mean_cumsum_scaled_transactions_arr: ndarray = np.mean(
            cumsum_scaled_transactions_arr, axis=1
        )
        cumsum_scaled_transactions_df["mean"] = mean_cumsum_scaled_transactions_arr
        if transactions_save_path is not None:
            cumsum_scaled_transactions_df.to_csv(str(transactions_save_path))
        if return_mean:
            return mean_cumsum_scaled_transactions_arr
        else:
            return None

    def calc_cumulative_transactions_per_session(
        self,
        transactions_save_folder_path: Path
    ) -> None:
        if (
            self._is_stacking_possible(self.ohlcv_dfs, "scaled_num_events") and
            self._is_stacking_possible(self.ohlcv_dfs, "session1_scaled_num_events") and
            self._is_stacking_possible(self.ohlcv_dfs, "session2_scaled_num_events")
        ):
            transactions_save_path: Path = transactions_save_folder_path / "cumsum_scaled_transactions.csv"
            self.calc_mean_cumulative_transactions(
                transactions_save_path, return_mean=False
            )
            transactions_session1_save_path: Path = transactions_save_folder_path / self.session1_transactions_file_name
            self.calc_mean_cumulative_transactions(
                transactions_session1_save_path, return_mean=False, session_name="session1"
            )
            transactions_session2_save_path: Path = transactions_save_folder_path / self.session2_transactions_file_name
            self.calc_mean_cumulative_transactions(
                transactions_session2_save_path, return_mean=False, session_name="session2"
            )
        else:
            raise ValueError(
                f"failed to stack dataframes."
            )

    def scatter_cumulative_transactions(
        self,
        img_save_name: str,
        color: str = "black",
    ) -> None:
        fig: Figure = plt.figure(figsize=(10,6))
        ax: Axes = fig.add_subplot(1,1,1)
        dummy_date = datetime.date(1990, 1, 1)
        for ohlcv_df in self.ohlcv_dfs:
            datetimes = [
                datetime.datetime.combine(dummy_date, t) for t in ohlcv_df.index
            ]
            cumsum_scaled_transactions_arr: ndarray = self._calc_cumsum_transactions_from_df(
                ohlcv_df, colname="scaled_num_events"
            )
            ax.scatter(
                datetimes, cumsum_scaled_transactions_arr,
                color=color, s=1
            )
        if self._is_stacking_possible(self.ohlcv_dfs, "scaled_num_events"):
            mean_cumsum_scaled_transactions_arr: ndarray = self.calc_mean_cumulative_transactions(
                return_mean=True
            )
            ax.plot(
                datetimes, mean_cumsum_scaled_transactions_arr, color="red"
            )
        else:
            warnings.warn(
                "Could not plot mean cumulative transactions."
            )
        ax.set_xlabel("time")
        ax.set_ylabel("cumulative number of transactions")
        ax.set_title("cumulative number of intraday transactions (scaled to 1)")
        ax.xaxis.set_major_locator(
            mdates.MinuteLocator(range(60), 60)
        )
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%H:%M")
        )
        if self.figs_save_path is None:
            raise ValueError(
                "specify directory: self.figs_save_path"
            )
        save_path: Path = self.figs_save_path / img_save_name
        plt.savefig(str(save_path))
