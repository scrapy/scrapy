"""
Similarity calculation for Instance based extraction algorithm.
"""
from itertools import izip, count
from operator import itemgetter
from heapq import nlargest

def common_prefix_length(a, b):
    """Calculate the length of the common prefix in both sequences passed.
    
    For example, the common prefix in this example is [1, 3]
    >>> common_prefix_length([1, 3, 4], [1, 3, 5, 1])
    2
    
    If there is no common prefix, 0 is returned
    >>> common_prefix_length([1], [])
    0
    """
    i = -1
    for i, x, y in izip(count(), a, b):
        if x != y:
            return i
    return i + 1

def common_prefix(*sequences):
    """determine the common prefix of all sequences passed
    
    For example:
    >>> common_prefix('abcdef', 'abc', 'abac')
    ['a', 'b']
    """
    prefix = []
    for sample in izip(*sequences):
        first = sample[0]
        if all(x == first for x in sample[1:]):
            prefix.append(first)
        else:
            break
    return prefix

def longest_unique_subsequence(to_search, subsequence, range_start=0, 
        range_end=None):
    """Find the longest unique subsequence of items in a list or array.  This
    searches the to_search list or array looking for the longest overlapping
    match with subsequence. If the largest match is unique (there is no other
    match of equivalent length), the index and length of match is returned.  If
    there is no match, (None, None) is returned.

    Please see section 3.2 of Extracting Web Data Using Instance-Based
    Learning by Yanhong Zhai and Bing Liu

    For example, the longest match occurs at index 2 and has length 3
    >>> to_search = [6, 3, 2, 4, 3, 2, 5]
    >>> longest_unique_subsequence(to_search, [2, 4, 3])
    (2, 3)
    
    When there are two equally long subsequences, it does not generate a match
    >>> longest_unique_subsequence(to_search, [3, 2])
    (None, None)

    range_start and range_end specify a range in which the match must begin
    >>> longest_unique_subsequence(to_search, [3, 2], 3)
    (4, 2)
    >>> longest_unique_subsequence(to_search, [3, 2], 0, 2)
    (1, 2)
    """
    startval = subsequence[0]
    if range_end is None:
        range_end = len(to_search)
    
    # the comparison to startval ensures only matches of length >= 1 and 
    # reduces the number of calls to the common_length function
    matches = ((i, common_prefix_length(to_search[i:], subsequence)) \
        for i in xrange(range_start, range_end) if startval == to_search[i])
    best2 = nlargest(2, matches, key=itemgetter(1))
    # if there is a single unique best match, return that
    if len(best2) == 1 or len(best2) == 2 and best2[0][1] != best2[1][1]:
        return best2[0]
    return None, None

def similar_region(extracted_tokens, template_tokens, labelled_region, 
        range_start=0, range_end=None):
    """Given a labelled section in a template, identify a similar region
    in the extracted tokens.

    The start and end index of the similar region in the extracted tokens
    is returned.

    This will return a tuple containing:
    (match score, start index, end index)
    where match score is the sum of the length of the matching prefix and 
    suffix. If there is no unique match, (0, None, None) will be returned.

    start_index and end_index specify a range in which the match must begin
    """
    data_length = len(extracted_tokens)
    if range_end is None:
        range_end = data_length
    # calculate the prefix score by finding a longest subsequence in 
    # reverse order
    reverse_prefix = template_tokens[labelled_region.start_index::-1]
    reverse_tokens = extracted_tokens[::-1]
    (rpi, pscore) = longest_unique_subsequence(reverse_tokens, reverse_prefix,
            data_length - range_end, data_length - range_start)

    # None means nothing exracted. Index 0 means there cannot be a suffix.
    if not rpi:
        return 0, None, None
    
    # convert to an index from the start instead of in reverse
    prefix_index = len(extracted_tokens) - rpi - 1

    if labelled_region.end_index is None:
        return pscore, prefix_index, None

    suffix = template_tokens[labelled_region.end_index:]

    # if it's not a paired tag, use the best match between prefix & suffix
    if labelled_region.start_index == labelled_region.end_index:
        (match_index, sscore) = longest_unique_subsequence(extracted_tokens,
            suffix, prefix_index, range_end)
        if match_index == prefix_index:
            return (pscore + sscore, prefix_index, match_index)
        elif pscore > sscore:
            return pscore, prefix_index, prefix_index
        elif sscore > pscore:
            return sscore, match_index, match_index
        return 0, None, None

    # calculate the suffix match on the tokens following the prefix. We could
    # consider the whole page and require a good match.
    (match_index, sscore) = longest_unique_subsequence(extracted_tokens,
            suffix, prefix_index + 1, range_end)
    if match_index is None:
        return 0, None, None
    return (pscore + sscore, prefix_index, match_index)
