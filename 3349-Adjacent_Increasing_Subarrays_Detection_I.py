class Solution(object):
    def hasIncreasingSubarrays(self, nums, k):
        """
        :type nums: List[int]
        :type k: int
        :rtype: bool
        """
        prev, cur, k2 = 0, 1, k*2
        for i in range(1, len(nums)):
            if nums[i-1] < nums[i]:
                cur += 1
            else:
                prev, cur = cur, 1
            if (cur >= k and prev >= k) or cur >= k2:
                return True
        return False
