# Copyright 2019, Hudson and Thames Quantitative Research
# All rights reserved
# Read more: https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/additional_information/license.html
"""
Utils for implementing partner selection approaches for vine copulas.
"""
# pylint: disable = invalid-name
import itertools
import numpy as np
import pandas as pd
import scipy


def get_sector_data(quadruple, constituents):
    """
    Function returns Sector and Sub sector information from tickers.
    """
    try:
        return constituents.loc[quadruple, ['Security', 'GICS Sector', 'GICS Sub-Industry']]
    except KeyError:
        return pd.DataFrame()


def get_sum_correlations_vectorized(data_subset: pd.DataFrame, all_possible_combinations: np.array) -> tuple:
    """
    Helper function for traditional approach to partner selection.
    Calculates sum of pairwise correlations between all stocks in the quadruple.

    :param data_subset: (pd.DataFrame) :
    :param all_possible_combinations: (np.array) :
    :return:
    """

    # Here the magic happens:
    # We use the combinations as an index
    corr_matrix_a = data_subset.values[:, all_possible_combinations]
    # corr_matrix_a has now the shape of (51, 19600, 4)
    # We now use take along axis to get the shape (4,19600,4), then we can sum the first and the last dimension
    corr_sums = np.sum(np.take_along_axis(corr_matrix_a, all_possible_combinations.T[..., np.newaxis], axis=0),
                       axis=(0, 2))

    d = all_possible_combinations.shape[-1]
    corr_sums = (corr_sums - d) / 2
    # this returns the shape of
    # (19600,1)
    # Afterwards we return the maximum index for the sums
    max_index = np.argmax(
        corr_sums)
    final_quadruple = data_subset.columns[list(all_possible_combinations[max_index])].tolist()

    return final_quadruple, corr_sums[max_index]


def multivariate_rho_vectorized(data_subset: pd.DataFrame, all_possible_combinations: np.array) -> tuple:
    """
    Helper function for extended approach to partner selection. Calculates 3 proposed estimators for
    high dimensional generalization for Spearman's rho. These implementations are present in
    Schmid, F., Schmidt, R., 2007. Multivariate extensions of Spearman’s rho and related statis-tics.

    """
    quadruples_combinations_data = data_subset.values[:, all_possible_combinations]

    n, _, d = quadruples_combinations_data.shape  # n : Number of samples, d : Number of stocks
    h_d = (d + 1) / (2 ** d - d - 1)

    # Calculating the first estimator of multivariate rho
    sum_1 = np.product(1 - quadruples_combinations_data, axis=-1).sum(axis=0)
    rho_1 = h_d * (-1 + (2 ** d / n) * sum_1)

    # Calculating the second estimator of multivariate rho
    sum_2 = np.product(quadruples_combinations_data, axis=-1).sum(axis=0)
    rho_2 = h_d * (-1 + (2 ** d / n) * sum_2)

    # Calculating the third estimator of multivariate rho
    pairs = np.array(list(itertools.combinations(range(d), 2)))
    k, l = pairs[:, 0], pairs[:, 1]
    sum_3 = ((1 - quadruples_combinations_data[:, :, k]) * (1 - quadruples_combinations_data[:, :, l])).sum(axis=(0, 2))
    dc2 = scipy.special.comb(d, 2, exact=True)
    rho_3 = -3 + (12 / (n * dc2)) * sum_3

    quadruples_scores = (rho_1 + rho_2 + rho_3) / 3
    # The quadruple scores have the shape of (19600,1) now
    max_index = np.argmax(quadruples_scores)

    final_quadruple = data_subset.columns[list(all_possible_combinations[max_index])].tolist()

    return final_quadruple, quadruples_scores[max_index]


def diagonal_measure_vectorized(data_subset: pd.DataFrame, all_possible_combinations: np.array) -> tuple:
    """
    Helper function for geometric approach to partner selection. Calculates the sum of Euclidean distances
    from the relative ranks to the (hyper-)diagonal in four dimensional space for a given target stock.

    Reference for calculating the euclidean distance from a point to diagonal
    https://in.mathworks.com/matlabcentral/answers/76727-how-can-i-calculate-distance-between-a-point-and-a-line-in-4d-or-space-higer-than-3d


    """

    quadruples_combinations_data = data_subset.values[:, all_possible_combinations]
    d = quadruples_combinations_data.shape[-1] # Shape : (n, 19600, d) where n : Number of samples, d : Number of stocks

    line = np.ones(d)
    # Einsum is great for specifying which dimension to multiply together
    # this extends the distance method for all 19600 combinations
    pp = (np.einsum("ijk,k->ji", quadruples_combinations_data, line) / np.linalg.norm(line))
    pn = np.sqrt(np.einsum('ijk,ijk->ji', quadruples_combinations_data, quadruples_combinations_data))
    distance_scores = np.sqrt(pn ** 2 - pp ** 2).sum(axis=1)
    min_index = np.argmin(distance_scores)
    final_quadruple = data_subset.columns[list(all_possible_combinations[min_index])].tolist()
    return final_quadruple, distance_scores[min_index]


def extremal_measure(u, co_variance_matrix):
    """
    Helper function to calculate chi-squared test statistic based on p-dimensional Nelsen copulas.
    Specifically, proposition 3.3 from Mangold (2015) is implemented for 4 dimensions.
    :param u: (pd.DataFrame) : ranked returns of stocks in quadruple.
    :param co_variance_matrix: (np.array) : Covariance matrix
    :return: test statistic
    """
    u = u.to_numpy()
    n = u.shape[0]

    # Calculating array T_(4,n) from proposition 3.3
    t = t_calc(u).mean(axis=1).reshape(-1, 1)  # Shape : (16, 1), Taking the mean w.r.t n
    # Calculating the final test statistic
    t_test_statistic = n * np.matmul(t.T, np.matmul(co_variance_matrix, t))
    return t_test_statistic[0, 0]


def get_co_variance_matrix():
    """
    Calculates 16x16 dimensional covariance matrix. Since the matrix is symmetric, only the integrals
    in the upper triangle are calculated. The remaining values are filled from the transpose.
    """
    co_variance_matrix = np.zeros((16, 16))
    for i, l1 in enumerate(itertools.product([1, 2], [1, 2], [1, 2], [1, 2])):
        for j, l2 in enumerate(itertools.product([1, 2], [1, 2], [1, 2], [1, 2])):
            if j < i:
                # Integrals in lower triangle are skipped.
                continue

            # Numerical Integration of 4 dimensions
            co_variance_matrix[i, j] = scipy.integrate.nquad(variance_integral_func, [(0, 1)] * 4, args=(l1, l2))[0]

    inds = np.tri(16, k=-1, dtype=bool)  # Storing the indices of elements in lower triangle.
    co_variance_matrix[inds] = co_variance_matrix.T[inds]
    return np.linalg.inv(co_variance_matrix)


def t_calc(u):
    """
    Calculates T_(4,n) as seen in proposition 3.3. Each of the 16 rows in the array are appended to output and
    returned as numpy array.
    :param u:
    :return: (np.array) of Shape (16, n)
    """
    output = []
    for l in itertools.product([1, 2], [1, 2], [1, 2], [1, 2]):
        # Equation form for each one of u1,u2,u3,u4 after partial differentials are calculated and multiplied
        # together.
        res = func(u[:, 0], l[0]) * func(u[:, 1], l[1]) * func(u[:, 2], l[2]) * func(u[:, 3], l[3])
        output.append(res)

    return np.array(output)  # Shape (16, n)


def func(t, value):
    """
    Function returns equation form of respective variable after partial differentiation.
    All variables in the differential equations are in one of two forms.
    :param t: (np.array) Variable
    :param value: (int) Flag denoting equation form of variable
    :return:
    """

    res = None
    if value == 1:
        res =  (t - 1) * (3 * t - 1)
    if value == 2:
        res =  t * (2 - 3 * t)

    return res


def variance_integral_func(u1, u2, u3, u4, l1, l2):
    """
    Calculates Integrand for covariance matrix calculation.
    """
    return func(u1, l1[0]) * func(u2, l1[1]) * func(u3, l1[2]) * func(u4, l1[3]) * \
           func(u1, l2[0]) * func(u2, l2[1]) * func(u3, l2[2]) * func(u4, l2[3])
