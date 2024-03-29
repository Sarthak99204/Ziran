#!/usr/bin/python
# make sure utils can be imported
import inspect
import os
import sys
sys.path.insert(0, os.path.dirname(inspect.getfile(lambda: None)))

# compare token identity and weight across multiple runs
import argparse
from functools import reduce
import json
import os
import warnings
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from tqdm import tqdm
from utils import _cite_me, _init_sp_tokeniser_variable_weights

def load_tokens(infile_path: str):
    with open(infile_path, "r") as infile:
        return json.load(infile)

def parse_tokens(token_info: list, index: int):
    return [j[index] for j in token_info for i in j]

def get_token_weight_map(token_info: list):
    token_weight_map = dict()
    for i in token_info:
        token_weight_map[i[0]] = i[1]
    return token_weight_map

def get_token_weight_intersect(token_weight_map: dict, intersection: set):
    weights_intersection = dict()
    for k, v in token_weight_map.items():
        if k in intersection:
            weights_intersection[k] = v
    return weights_intersection

def main():
    parser = argparse.ArgumentParser(
        description='Take token json files, show intersection and weight variance.'
    )
    parser.add_argument('infile_paths', type=str, nargs="+",
                        help='path to tokeniser files generated by tokenise_bio')
    parser.add_argument('-t', '--tokeniser_path', type=str, default="pooled.json",
                        help='path to pooled tokeniser (DEFAULT: pooled.json)')    
    parser.add_argument('-w', '--token_weight', type=str, default="token_weights.tsv",
                        help='path to output file showing token weights status')
    parser.add_argument('-m', '--merge_strategy', type=str, default=None,
                        help='merge tokens using [ inner | outer ] (DEFAULT: None)')    
    parser.add_argument('-p', '--pooling_strategy', type=str, default=None,
                        help='pool tokens using [ mean | median | max | min ] (DEFAULT: None)')
    parser.add_argument('-o', '--outfile_path', type=str, default="token_dist.pdf",
                        help='path to output boxplot showing token weights distribution')
    
    args = parser.parse_args()
    infile_paths = args.infile_paths
    tokeniser_path = args.tokeniser_path
    token_weight = args.token_weight
    merge_strategy = args.merge_strategy
    pooling_strategy = args.pooling_strategy    
    outfile_path = args.outfile_path
    
    i = " ".join([i for i in sys.argv[0:]])
    print("COMMAND LINE ARGUMENTS FOR REPRODUCIBILITY:\n\n\t", i, "\n")

    vocab_all = [load_tokens(i)["model"]["vocab"] for i in infile_paths]
    tokens_all = [set(i) for i in [parse_tokens(i, 0) for i in vocab_all]]
    token_weight_map = [get_token_weight_map(i) for i in vocab_all]

    tokens_per_set = [len(i) for i in tokens_all]
    tokens_intersection = set.intersection(*tokens_all)
    tokens_union = set.union(*tokens_all)
    print("\nTokens per set (first 100):", tokens_per_set[:100], "\n")
    print("\nTokens intersection count:", len(tokens_intersection), "\n")
    print("\nTokens union count:", len(tokens_union), "\n")

    if merge_strategy != None:
        tokens = [
            pd.DataFrame(i, columns=['token', 'weight']).set_index('token') for i in vocab_all
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tokens = reduce(
                lambda left, right: pd.merge(
                    left, 
                    right, 
                    left_index=True, 
                    right_index=True, 
                    how=merge_strategy,
                    ), 
                    tokens
                )
            
        if pooling_strategy == "mean":
            tokens[pooling_strategy] = tokens.mean(axis=1)
        if pooling_strategy == "median":
            tokens[pooling_strategy] = tokens.median(axis=1)
        if pooling_strategy == "max":
            tokens[pooling_strategy] = tokens.max(axis=1)
        if pooling_strategy == "min":
            tokens[pooling_strategy] = tokens.min(axis=1)
        tokens = tokens[pooling_strategy].dropna().to_dict()

        tokeniser = _init_sp_tokeniser_variable_weights(tokens)
        with open(tokeniser_path, mode="w") as token_out:
            json.dump(tokeniser, token_out, ensure_ascii=False, indent=4)

    weights_intersection = [
        get_token_weight_intersect(i, tokens_intersection) for i in token_weight_map
        ]
    data = pd.DataFrame(weights_intersection)
    std = std_of_std = data.describe().iloc[2]
    std_of_std = data.describe().iloc[2].describe()
    std_25 = std_of_std.iloc[4]
    std_75 = std_of_std.iloc[6]
    std_iqr = std_75 - std_25
    outliers_low = std_25 - (1.5 * std_iqr)
    outliers_high = std_75 + (1.5 * std_iqr)
    print("\nOutlier thresholds (low, high):", outliers_low, outliers_high)

    # filter out high variance tokens and report
    tokens_outliers = std[(std < outliers_low) | (std > outliers_high)]
    tokens_inliers = std[~((std < outliers_low) | (std > outliers_high))]
    print("\nHigh variance tokens:\n", tokens_outliers)

    tokens_outliers = pd.DataFrame(tokens_outliers)
    tokens_inliers = pd.DataFrame(tokens_inliers)
    tokens_outliers["is_outlier"] = True
    tokens_inliers["is_outlier"] = False
    tokens_status = pd.concat([tokens_outliers, tokens_inliers], axis=0)
    weights_all = data.T
    weights_all.columns = infile_paths
    tokens_status_weights = tokens_status.merge(
        weights_all, left_index=True, right_index=True, sort=True
        )
    tokens_status_weights.sort_values(
        ["is_outlier", "std"], axis=0, ascending=False, inplace=True
        )
    tokens_status_weights.to_csv(token_weight, sep="\t")

    # estimate figure length on number of tokens (3.5 per plot seems ok)
    est_len = len(tokens_intersection) / 3.5
    fig, ax = plt.subplots(figsize=(8.27, est_len), dpi=300)
    sns.boxplot(ax=ax, data=data, orient="h")
    ax.set_title("Token distribution plot")
    ax.set_xlabel("Tokens")
    ax.set_ylabel("Weights")
    ax.set_xticklabels([])
    fig.savefig(outfile_path, format="pdf", dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    main()
    _cite_me()
