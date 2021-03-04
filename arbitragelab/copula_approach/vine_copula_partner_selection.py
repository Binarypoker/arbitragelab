# Copyright 2019, Hudson and Thames Quantitative Research
# All rights reserved
# Read more: https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/additional_information/license.html
"""
Module for implementing partner selection approaches for vine copulas.
"""
# pylint: disable = invalid-name
import itertools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from statsmodels.distributions.empirical_distribution import ECDF
from arbitragelab.copula_approach.vine_copula_partner_selection_utils import extremal_measure, \
    get_co_variance_matrix, get_sum_correlations_vectorized, diagonal_measure_vectorized, multivariate_rho_vectorized


class PartnerSelection:
    """
    Implementation of the Partner Selection procedures proposed in Section 3.1.1 in the following paper.

    3 partner stocks are selected for a target stock based on four different approaches namely, Traditional approach,
    Extended approach, Geometric approach and Extremal approach.

    `Stübinger, J., Mangold, B. and Krauss, C., 2018. Statistical arbitrage with vine copulas. Quantitative Finance, 18(11), pp.1831-1849.
    <https://www.econstor.eu/bitstream/10419/147450/1/870932616.pdf>`__
    """

    def __init__(self, prices: pd.DataFrame):
        """
        Inputs the price series required for further calculations.
        Also includes preprocessing steps described in the paper, before starting the Partner Selection procedures.
        These steps include, finding the returns and ranked returns of the stocks, and calculating the top 50
        correlated stocks for each stock in the universe.

        :param prices: (pd.DataFrame): Contains price series of all stocks in universe
        """

        if len(prices) == 0:
            raise Exception("Input does not contain any data")

        if not isinstance(prices, pd.DataFrame):
            raise Exception("Partner Selection Class requires a pandas DataFrame as input")

        self.universe = prices  # Contains daily prices for all stocks in universe.
        self.returns, self.ranked_returns = self._get_returns()  # Daily returns and corresponding ranked returns.

        # Correlation matrix containing all stocks in universe
        self.correlation_matrix = self._correlation()
        # For each stock in universe, tickers of top 50 most correlated stocks are stored
        self.top_50_correlations = self._top_50_tickers()
        # Quadruple combinations for all stocks in universe
        self.all_quadruples = self._generate_all_quadruples()

    def _correlation(self) -> pd.DataFrame:
        """
        Calculates correlation between all stocks in universe.

        :return: (pd.DataFrame) : Correlation Matrix
        """

        return self.ranked_returns.corr(method='pearson')  # Pearson or spearman,we get same results as input is ranked

    def _get_returns(self) -> (pd.DataFrame, pd.DataFrame):
        """
        Calculating daily returns and ranked daily returns of the stocks.

        :return (tuple):
            returns_df : (pd.DataFrame) : Dataframe consists of daily returns
            returns_df_ranked : (pd.DataFrame) : Dataframe consists of ranked daily returns between [0,1]
        """

        returns_df = self.universe.pct_change()
        returns_df = returns_df.replace([np.inf, -np.inf], np.nan).ffill().dropna()

        # Calculating rank of daily returns for each stock. 'first' method is used to assign ranks in order they appear
        returns_df_ranked = returns_df.rank(axis=0, method='first', pct=True)
        return returns_df, returns_df_ranked

    def _top_50_tickers(self) -> pd.DataFrame:
        """
        Calculates the top 50 correlated stocks for each target stock.

        :return: (pd.DataFrame) : Dataframe consisting of 50 columns for each stock in the universe
        """

        def tickers_list(col):
            """
            Returns list of tickers ordered according to correlations with target.
            """
            # Sort the column data in descending order and return the index of top 50 rows.
            return col.sort_values(ascending=False)[1:51].index.to_list()

        # Returns DataFrame with all stocks as indices and their respective top 50 correlated stocks as columns.
        return self.correlation_matrix.apply(tickers_list, axis=0).T

    def _generate_all_quadruples(self) -> pd.DataFrame:
        """
         Method generates unique quadruples for all target stocks in universe.

         :return: (pd.DataFrame) : consists of all quadruples for every target stock
         """

        return self.top_50_correlations.apply(self._generate_all_quadruples_helper, axis=1)

    @staticmethod
    def _generate_all_quadruples_helper(row: pd.Series) -> list:
        """
         Helper function which generates unique quadruples for each target stock.

         :param row: (pd.Series) : list of 50 partner stocks
         :return: (list) : quadruples
         """

        target = row.name
        quadruples = []
        for triple in itertools.combinations(row, 3):
            quadruples.append([target] + list(triple))
        return quadruples

    @staticmethod
    def _prepare_combinations_of_partners(stock_selection: list) -> np.array:
        """Helper function to calculate all combinations for a target stock and it's potential partners
        :param: stock_selection (pd.DataFrame): the target stock has to be the first element of the array
        :return: the possible combinations for the quadruples.Shape (19600,4) or
        if the target stock is left out (19600,3)
        """
        # We will convert the stock names into integers and then get a list of all combinations with a length of 3
        num_of_stocks = len(stock_selection)
        # We turn our partner stocks into numerical indices so we can use them directly for indexing
        partner_stocks_idx = np.arange(1, num_of_stocks)  # basically exclude the target stock
        partner_stocks_idx_combs = itertools.combinations(partner_stocks_idx, 3)
        return np.array(list((0,) + comb for comb in partner_stocks_idx_combs))

    # Method 1
    def traditional(self, n_targets=5) -> list:
        """
        This method implements the first procedure described in Section 3.1.1.
        For all possible quadruples of a given stock, we calculate the sum of all pairwise correlations.
        For every target stock the quadruple with the highest sum is returned.

        :param n_targets: (int) : number of target stocks to select
        :return output_matrix: list: List of all selected quadruples
        """

        output_matrix = []  # Stores the final set of quadruples.
        # Iterating on the top 50 indices for each target stock.
        for target in self.top_50_correlations.index[:n_targets]:

            stock_selection = [target] + self.top_50_correlations.loc[target].tolist()
            data_subset = self.correlation_matrix.loc[stock_selection, stock_selection]
            all_possible_combinations = self._prepare_combinations_of_partners(stock_selection)

            final_quadruple = get_sum_correlations_vectorized(data_subset, all_possible_combinations)[0]
            # Appending the final quadruple for each target to the output matrix
            output_matrix.append(final_quadruple)

        return output_matrix

    # Method 2
    def extended(self, n_targets=5) -> list:
        """
        This method implements the second procedure described in Section 3.1.1.
        It involves calculating the multivariate version of Spearman's correlation
        for all possible quadruples of a given stock.
        For every target stock the quadruple with the highest correlation is returned.

        :param n_targets: (int) : number of target stocks to select
        :return output_matrix: list: List of all selected quadruples
        """

        ecdf_df = self.returns.apply(lambda x: ECDF(x)(x), axis=0)

        output_matrix = []  # Stores the final set of quadruples.
        # Iterating on the top 50 indices for each target stock.
        for target in self.top_50_correlations.index[:n_targets]:
            stock_selection = [target] + self.top_50_correlations.loc[target].tolist()
            data_subset = ecdf_df[stock_selection]
            all_possible_combinations = self._prepare_combinations_of_partners(stock_selection)

            final_quadruple = multivariate_rho_vectorized(data_subset, all_possible_combinations)[0]
            # Appending the final quadruple for each target to the output matrix
            output_matrix.append(final_quadruple)

        return output_matrix

    # Method 3
    def geometric(self, n_targets=5) -> list:
        """
        This method implements the third procedure described in Section 3.1.1.
        It involves calculating the four dimensional diagonal measure for all possible quadruples of a given stock.
        For every target stock the quadruple with the lowest diagonal measure is returned.

        :param n_targets: (int) : number of target stocks to select
        :return output_matrix: list: List of all selected quadruples
        """

        output_matrix = []  # Stores the final set of quadruples.
        # Iterating on the top 50 indices for each target stock.
        for target in self.top_50_correlations.index[:n_targets]:
            stock_selection = [target] + self.top_50_correlations.loc[target].tolist()
            data_subset = self.ranked_returns[stock_selection]
            all_possible_combinations = self._prepare_combinations_of_partners(stock_selection)

            final_quadruple = diagonal_measure_vectorized(data_subset, all_possible_combinations)[0]
            # Appending the final quadruple for each target to the output matrix
            output_matrix.append(final_quadruple)

        return output_matrix

    # Method 4
    def extremal(self, n_targets=5) -> list:
        """
        This method implements the fourth procedure described in Section 3.1.1.
        It involves calculating a non-parametric test statistic based on Mangold (2015) to measure the
        degree of deviation from independence. Main focus of this measure is the occurrence of joint extreme events.

        :param n_targets: (int) : number of target stocks to select
        :return output_matrix: list: List of all selected quadruples
        """

        co_variance_matrix = get_co_variance_matrix()
        output_matrix = []  # Stores the final set of quadruples.
        # Iterating on the top 50 indices for each target stock.
        for target in self.top_50_correlations.index[:n_targets]:
            max_measure = -np.inf  # Variable used to extract the desired maximum value
            final_quadruple = None  # Stores the final desired quadruple

            # Iterating on all unique quadruples generated for a target
            for quadruple in self.all_quadruples[target]:
                measure = extremal_measure(self.ranked_returns[quadruple], co_variance_matrix)
                if measure > max_measure:
                    max_measure = measure
                    final_quadruple = quadruple
            # Appending the final quadruple for each target to the output matrix
            output_matrix.append(final_quadruple)

        return output_matrix

    def plot_selected_pairs(self, quadruples: list):
        """
        Plots the final selection of quadruples.
        :param quadruples: List of quadruples
        """

        if quadruples is None:
            raise Exception("Input list is empty")

        _, axs = plt.subplots(len(quadruples),
                                figsize=(15, 3 * len(quadruples)))

        plt.subplots_adjust(hspace=0.6)

        if len(quadruples) == 1:
            quadruple = quadruples[0]
            data = self.universe.loc[:, quadruple].apply(lambda x: np.log(x).diff()).cumsum()
            sns.lineplot(ax=axs, data=data, legend=quadruple)
            axs.set_title(f'Final Quadruple of stocks with {quadruple[0]} as target')
            axs.set_ylabel('Cumulative Daily Returns')
        else:
            for i, quadruple in enumerate(quadruples):
                data = self.universe.loc[:, quadruple].apply(lambda x: np.log(x).diff()).cumsum()
                sns.lineplot(ax=axs[i], data=data, legend=quadruple)
                axs[i].set_title(f'Final Quadruple of stocks with {quadruple[0]} as target')
                axs[i].set_ylabel('Cumulative Daily Returns')

        return axs
