"""
Tax keyword detection and classification for Slovenian tax content.
"""

import re
from typing import List, Dict, Set


class TaxKeywordFilter:
    """
    Detects and classifies tax-related content using Slovenian tax terminology.

    Categories:
        - individual: Personal income tax (dohodnina)
        - s.p.: Sole proprietor (samostojni podjetnik)
        - d.o.o.: Limited liability company
        - general: General tax topics
    """

    # Slovenian tax keywords by category
    KEYWORDS = {
        "individual": [
            # Income tax
            "dohodnina", "dohodnine", "dohodninski",
            "osebni dohodek", "osebnega dohodka",
            "davčna olajšava", "davčne olajšave",
            "letna davčna napoved", "napoved dohodnine",
            "informativni izračun",
            # Deductions
            "posebna olajšava", "splošna olajšava",
            "vzdrževani družinski član",
            # Types of income
            "dohodek iz zaposlitve", "dohodek iz dejavnosti",
            "dohodek iz kapitala", "dividende",
            "obresti", "kapitalski dobiček",
            "dohodek iz oddajanja premoženja",
            "najemnina", "avtorski honorar",
        ],
        "s.p.": [
            # SP basics
            "samostojni podjetnik", "s.p.", "sp",
            "samostojna dejavnost", "samostojnega podjetnika",
            # SP taxation
            "normirani odhodki", "normiranci", "normiranec",
            "pavšalna obdavčitev", "dejanski stroški",
            "popoldanski s.p.", "popoldanski sp",
            # SP obligations - with Slovenian declensions
            "prispevki za socialno varnost", "prispevke za socialno varnost",
            "prispevkov za socialno varnost", "socialni prispevki",
            "obvezno zavarovanje", "pizs", "zpiz",
            "vodenje poslovnih knjig",
            "davčni obračun akontacije",
            "akontacija dohodnine",
        ],
        "d.o.o.": [
            # Company types
            "d.o.o.", "doo", "družba z omejeno odgovornostjo",
            "kapitalska družba", "gospodarska družba",
            # Corporate tax
            "davek od dohodkov pravnih oseb", "ddpo",
            "davčna osnova pravne osebe",
            "bilančni dobiček", "obdavčljivi dobiček",
            # Corporate specifics
            "poslovni delež", "osnovni kapital",
            "izplačilo dobička", "delitev dobička",
            "transfer pricing", "transferne cene",
            "davčno priznani odhodki",
        ],
        "general": [
            # General tax terms
            "davek", "davki", "davčni", "davščina",
            "obdavčitev", "obdavčenje",
            "furs", "finančna uprava",
            "davčni zavezanec", "davčna obveznost",
            "davčna napoved", "davčni obračun",
            # Tax types
            "ddv", "davek na dodano vrednost",
            "davek na promet", "trošarina",
            "davek na nepremičnine", "nadomestilo za uporabo stavbnega zemljišča",
            # Procedures
            "davčni postopek", "davčna izvršba",
            "davčni inšpekcijski nadzor", "samoprijava",
            "zastaranje davčne obveznosti",
            # Deadlines
            "rok za oddajo", "rok za plačilo",
            "akontacija", "poračun",
            # Documentation
            "edavki", "račun", "faktura",
            "knjiga prihodkov", "knjiga odhodkov",
        ],
    }

    # Compile patterns for efficiency
    def __init__(self):
        self._compiled_patterns = {}
        for category, keywords in self.KEYWORDS.items():
            patterns = [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in keywords]
            self._compiled_patterns[category] = patterns

        # All keywords for general tax-relatedness check
        all_keywords = []
        for keywords in self.KEYWORDS.values():
            all_keywords.extend(keywords)
        self._all_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            for kw in all_keywords
        ]

    def is_tax_related(self, text: str, min_matches: int = 1) -> bool:
        """
        Check if text contains tax-related content.

        Args:
            text: Text to analyze
            min_matches: Minimum keyword matches required

        Returns:
            True if text is tax-related
        """
        if not text:
            return False

        matches = sum(1 for p in self._all_patterns if p.search(text))
        return matches >= min_matches

    def find_keywords(self, text: str) -> List[str]:
        """
        Find all tax keywords present in text.

        Args:
            text: Text to analyze

        Returns:
            List of found keywords
        """
        if not text:
            return []

        found = []
        for category, patterns in self._compiled_patterns.items():
            for i, pattern in enumerate(patterns):
                if pattern.search(text):
                    found.append(self.KEYWORDS[category][i])

        return list(set(found))

    def classify(self, text: str) -> Dict[str, any]:
        """
        Classify text by tax category and extract topics.

        Args:
            text: Text to analyze

        Returns:
            Dict with 'category' and 'tax_topics'
        """
        if not text:
            return {"category": "general", "tax_topics": []}

        # Count matches per category
        category_scores = {}
        found_keywords = []

        for category, patterns in self._compiled_patterns.items():
            score = 0
            for i, pattern in enumerate(patterns):
                if pattern.search(text):
                    score += 1
                    found_keywords.append(self.KEYWORDS[category][i])
            category_scores[category] = score

        # Determine primary category (excluding 'general' unless it's the only one)
        specific_categories = {k: v for k, v in category_scores.items() if k != "general"}

        if any(v > 0 for v in specific_categories.values()):
            # Has specific category matches
            primary_category = max(specific_categories, key=specific_categories.get)
            if specific_categories[primary_category] == 0:
                primary_category = "general"
        else:
            primary_category = "general"

        return {
            "category": primary_category,
            "tax_topics": list(set(found_keywords)),
        }

    def get_category_keywords(self, category: str) -> List[str]:
        """Get all keywords for a specific category."""
        return self.KEYWORDS.get(category, [])

    @classmethod
    def add_keywords(cls, category: str, keywords: List[str]):
        """
        Add custom keywords to a category.

        Args:
            category: Category name
            keywords: List of keywords to add
        """
        if category not in cls.KEYWORDS:
            cls.KEYWORDS[category] = []
        cls.KEYWORDS[category].extend(keywords)
