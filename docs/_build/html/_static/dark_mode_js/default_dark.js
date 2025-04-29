const loadTheme = () => {
  let theme = localStorage.getItem('theme');

  if (theme !== null) {
    if (theme === 'dark')
      document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    localStorage.setItem('theme', 'dark');
    document.documentElement.setAttribute('data-theme', 'dark');
  }
};

loadTheme();
