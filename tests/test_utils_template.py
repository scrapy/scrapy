import scrapy
from os.path import exists, join, abspath, dirname
from shutil import rmtree, copytree, move
from tempfile import mkdtemp
from twisted.trial import unittest
from scrapy.utils.template import get_template_dir
from scrapy.utils.test import get_crawler

__doctests__ = ['scrapy.utils.template']


class TemplateDirTest(unittest.TestCase):

    def setUp(self):
        self.settings = get_crawler().settings
        self.proj_path = mkdtemp()
        copytree(self.settings['TEMPLATES_DIR_BASE'][1], join(self.proj_path, "templates"))
        self.template_folder = join(self.proj_path, "templates")

    def tearDown(self):
        rmtree(self.proj_path)

    def test_standard(self, template_type="project"):
        option1 = join(self.settings['TEMPLATES_DIR_BASE'][0], template_type)
        option2 = join(self.settings['TEMPLATES_DIR_BASE'][1], template_type)
        if(exists(option1)):
            self.assertEqual(option1, get_template_dir(self.settings, template_type))

        if(exists(option2)):
            temp = self.settings['TEMPLATES_DIR_BASE'][0]
            self.settings['TEMPLATES_DIR_BASE'][0] = ""
            self.assertEqual(option2, get_template_dir(self.settings, template_type))
            self.settings['TEMPLATES_DIR_BASE'][0] = temp

    def test_standard_spiders(self):
        self.test_standard(template_type="spiders")

    def test_different_dir(self, template_type="project"):
        settings = get_crawler(settings_dict={
            'TEMPLATES_DIR': self.template_folder
            }).settings
        expected_output = join(self.template_folder, template_type)
        self.assertEqual(get_template_dir(settings, template_type), expected_output)

    def test_different_dir_spiders(self):
        self.test_different_dir(template_type="spiders")

    def test_different_folder_name(self, template_type="project"):
        current_dir = join(self.template_folder, template_type)
        move(current_dir, current_dir + "_new")
        if template_type == "project":
            settings = get_crawler(settings_dict={
                'TEMPLATES_DIR': self.template_folder,
                'TEMPLATES_PROJECT': template_type + "_new"
                }).settings
        else:
            settings = get_crawler(settings_dict={
                'TEMPLATES_DIR': self.template_folder,
                'TEMPLATES_SPIDERS': template_type + "_new"
                }).settings
        expected_output = current_dir + "_new"
        self.assertEqual(get_template_dir(settings, template_type), expected_output)

    def test_different_folder_name_spiders(self):
        self.test_different_folder_name(template_type="spiders")

if __name__ == "__main__":
    unittest.main()
