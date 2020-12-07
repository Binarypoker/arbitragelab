# Copyright 2019, Hudson and Thames Quantitative Research
# All rights reserved
# Read more: https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/additional_information/license.html
"""
Back end module that handles maximum likelihood related copula calculations.

Functions include:
    Finding (marginal) cumulative distribution function from data.
    Maximum likelihood estimation of theta_hat (empirical theta) from data.
    Calculating the sum log-likelihood given a copula and data.
    Calculating SIC (Schwarz information criterion).
    Calculating AIC (Akaike information criterion).
    Calculating HQIC (Hannan-Quinn information criterion).
"""
# pylint: disable = invalid-name
from typing import Callable
import numpy as np
import scipy.stats as ss
from statsmodels.distributions.empirical_distribution import ECDF
from sklearn.covariance import EmpiricalCovariance

import arbitragelab.copula_approach.copula_generate as cg


def find_marginal_cdf(x: np.array, empirical: bool = True, **kwargs) -> Callable[[float], float]:
    """
    Find the cumulative density function (CDF). i.e., P(X<=x).

    User can choose between an empirical CDF or a CDF selected by maximum likelihood.

    :param x: (np.array) Data. Will be scaled to [0, 1].
    :param empirical: (bool) Whether to use empirical estimation for CDF.
    :param kwargs: (dict) Setting the floor and cap of probability.
        prob_floor: (float) Probability floor.
        prob_cap: (float) Probability cap.
    :return fitted_cdf: (func) The cumulative density function from data.
    """

    # Make sure it is an np.array.
    x = np.array(x)

    prob_floor = kwargs.get('prob_floor', 0.00001)
    prob_cap = kwargs.get('prob_cap', 0.99999)

    if empirical:
        # Use empirical cumulative density function on data.
        fitted_cdf = lambda data: max(min(ECDF(x)(data), prob_cap), prob_floor)
        # Vectorize so it works on an np.array.
        v_fitted_cdf = np.vectorize(fitted_cdf)
        return v_fitted_cdf

    return None


def ml_theta_hat(x: np.array, y: np.array, copula_name: str) -> float:
    """
    Calculate empirical theta (theta_hat) for a type of copula by maximum likelihood.

    x, y need to be uniformly distributed respectively. Use Kendall's tau value to
    calculate theta hat.

    Note: Gaussian and Student-t copula do not use this function.

    :param x: (np.array) 1D vector data.
    :param y: (np.array) 1D vector data.
    :param copula_name: (str) Name of the copula.
    :return theta_hat: (float) Empirical theta for the copula.
    """

    # Calculate Kendall's tau from data.
    tau = ss.kendalltau(x, y)[0]

    # Calculate theta from the desired copula.
    dud_cov = [[1, 0], [0, 1]]  # To create copula by name. Not involved in calculations.

    # Create copula by its name. Fulfil switch functionality.
    switch = cg.Switcher()
    my_copula = switch.choose_copula(copula_name=copula_name,
                                     cov=dud_cov)

    # Translate Kendall's tau into theta.
    theta_hat = my_copula.theta_hat(tau)

    return theta_hat


def log_ml(x: np.array, y: np.array, copula_name: str, nu: float = None) -> tuple:
    """
    Fit a type of copula using maximum likelihood.

    User provides the name of the copula (and degree of freedom nu, if it is 'Student-t'), then this method
    fits the copula type by maximum likelihood. Moreover, it calculates log maximum likelihood.

    :param x: (np.array) 1D vector data. Need to be uniformly distributed.
    :param y: (np.array) 1D vector data. Need to be uniformly distributed.
    :param copula_name: (str) Name of the copula.
    :param nu: (float) Degree of freedom for Student-t copula.
    :return: (tuple)
        log_likelihood_sum: (float) Logarithm of max likelihood value from data.
        my_copula: (Copula) Copula with its parameter fitted to data.
    """

    theta_copula_names = ['Gumbel', 'Clayton', 'Frank', 'Joe', 'N13', 'N14']
    # Find log max likelihood given all the data.
    switch = cg.Switcher()

    if copula_name in theta_copula_names:
        # Get the max likelihood theta_hat for theta from data.
        theta = ml_theta_hat(x, y, copula_name)
        my_copula = switch.choose_copula(copula_name=copula_name,
                                         theta=theta)

    if copula_name == 'Gaussian':
        # 1. Calculate covariance matrix using sklearn.
        # Correct matrix dimension for fitting in sklearn.
        unif_data = np.array([x, y]).reshape(2, -1).T
        value_data = ss.norm.ppf(unif_data)  # Change from quantile to value.
        # Getting empirical covariance matrix.
        cov_hat = EmpiricalCovariance().fit(value_data).covariance_

        # 2. Construct copula with fitted parameter.
        my_copula = switch.choose_copula(copula_name=copula_name,
                                         cov=cov_hat)

    if copula_name == 'Student':
        # 1. Calculate covariance matrix using sklearn.
        # Correct matrix dimension for fitting in sklearn.
        unif_data = np.array([x, y]).reshape(2, -1).T
        t_dist = ss.t(df=nu)
        value_data = t_dist.ppf(unif_data)  # Change from quantile to value.
        # Getting empirical covariance matrix.
        cov_hat = EmpiricalCovariance().fit(value_data).covariance_

        # 2. Construct copula with fitted parameter.
        my_copula = switch.choose_copula(copula_name=copula_name,
                                         cov=cov_hat,
                                         nu=nu)

    # Likelihood quantity for each pair of data, stored in a list.
    likelihood_list = [my_copula.c(xi, yi) for (xi, yi) in zip(x, y)]
    # Sum of logarithm of likelihood data.
    log_likelihood_sum = np.sum(np.log(likelihood_list))

    return log_likelihood_sum, my_copula


def sic(log_likelihood: float, n: int, k: int = 1) -> float:
    """
    Schwarz information criterion (SIC), aka Bayesian information criterion (BIC).

    :param log_likelihood: (float) Sum of log-likelihood of some data.
    :param n: (int) Number of instances.
    :param k: (int) Number of parameters estimated by max likelihood.
    :return sic_value: (float) Value of SIC.
    """

    sic_value = np.log(n)*k - 2*log_likelihood

    return sic_value


def aic(log_likelihood: float, n: int, k: int = 1) -> float:
    """
    Akaike information criterion.

    :param log_likelihood: (float) Sum of log-likelihood of some data.
    :param n: (int) Number of instances.
    :param k: (int) Number of parameters estimated by max likelihood.
    :return sic_value (float): Value of AIC.
    """

    aic_value = (2*n/(n-k-1))*k - 2*log_likelihood

    return aic_value


def hqic(log_likelihood: float, n: int, k: int = 1) -> float:
    """
    Hannan-Quinn information criterion.

    :param log_likelihood: (float) Sum of log-likelihood of some data.
    :param n: (int) Number of instances.
    :param k: (int) Number of parameters estimated by max likelihood.
    :return sic_value (float): Value of HQIC.
    """

    hqic_value = 2*np.log(np.log(n))*k - 2*log_likelihood

    return hqic_value
