import unittest

listArr = []
with open('numbers.txt', 'r') as file:
    for row in file:
        listArr.append(row)

expected_vals = ['3375', '3679', '3680', '4345', '4841', '13749', '17820', '38378', '42846', '42952']


class MyTestCase(unittest.TestCase):
    def test_value01(self):
        # avoid the \n delimiter with -1
        val = listArr[0][0:-1]
        trueVal = '3375'
        self.assertEqual(val, trueVal)

    def test_value01f(self):
        # avoid the \n delimiter with -1
        val = listArr[0][0:-1]
        notTrueVal = '3376'
        self.assertNotEqual(val, notTrueVal)

    def test_value02(self):
        # avoid the \n delimiter with -1
        val = listArr[1][0:-1]
        trueVal = expected_vals[1]
        self.assertEqual(val, trueVal)

    def test_value02f(self):
        # avoid the \n delimiter with -1
        val = listArr[1][0:-1]
        notTrueVal = '123'
        self.assertNotEqual(val, notTrueVal)

    def test_value03(self):
        # avoid the \n delimiter with -1
        val = listArr[2][0:-1]
        trueVal = expected_vals[2]
        self.assertEqual(val, trueVal)

    def test_value03f(self):
        # avoid the \n delimiter with -1
        val = listArr[2][0:-1]
        notTrueVal = '4332'
        self.assertNotEqual(val, notTrueVal)

    def test_value04(self):
        # avoid the \n delimiter with -1
        val = listArr[3][0:-1]
        trueVal = expected_vals[3]
        self.assertEqual(val, trueVal)

    def test_value04f(self):
        # avoid the \n delimiter with -1
        val = listArr[3][0:-1]
        notTrueVal = '0000'
        self.assertNotEqual(val, notTrueVal)

    def test_value05(self):
        # avoid the \n delimiter with -1
        val = listArr[4][0:-1]
        trueVal = expected_vals[4]
        self.assertEqual(val, trueVal)

    def test_value05f(self):
        # avoid the \n delimiter with -1
        val = listArr[4][0:-1]
        notTrueVal = '3243'
        self.assertNotEqual(val, notTrueVal)

    def test_value06(self):
        # avoid the \n delimiter with -1
        val = listArr[5][0:-1]
        trueVal = expected_vals[5]
        self.assertEqual(val, trueVal)

    def test_value07(self):
        # avoid the \n delimiter with -1
        val = listArr[6][0:-1]
        trueVal = expected_vals[6]
        self.assertEqual(val, trueVal)

    def test_value08(self):
        # avoid the \n delimiter with -1
        val = listArr[7][0:-1]
        trueVal = expected_vals[7]
        self.assertEqual(val, trueVal)

    def test_value09(self):
        # avoid the \n delimiter with -1
        val = listArr[8][0:-1]
        trueVal = expected_vals[8]
        self.assertEqual(val, trueVal)

    def test_value10(self):
        # avoid the \n delimiter with -1
        val = listArr[9][0:-1]
        trueVal = expected_vals[9]
        self.assertEqual(val, trueVal)

if __name__ == '__main__':
    unittest.main()
