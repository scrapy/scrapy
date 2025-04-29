var mathjax = false;
var sphinxtabs = false;



function reRenderTooltip (instance, helper) {
    // Check if the content is the same as the default content until
    // it's different. Once it's different, re renders its content
    // to show it properly (this may involve calling external JS
    // libraries like MathJax) and finally call tooltip.reposition().
    if (helper.tooltip.textContent !== 'Loading...') {
        // https://stackoverflow.com/questions/5200545/how-to-recall-or-restart-mathjax
        if (mathjax) {
            if (typeof MathJax !== 'undefined') {
                reLoadMathJax(helper.tooltip.id);
            } else {
                console.debug('Not triggering MathJax because it is not defined');
            };

        };
        instance.reposition();
    } else {
        setTimeout(reRenderTooltip, 100, instance, helper);
    };
}


function reLoadMathJax(elementId) {
    if (parseInt(MathJax.version[0]) >= 3) {
        console.debug('Typesetting for Mathjax3');
        MathJax.typeset();
    } else {
        console.debug('Typesetting for MathJax2');
        MathJax.Hub.Queue((["Typeset", MathJax.Hub, elementId]));
    }
}


function reLoadSphinxTabs() {
    if (sphinxtabs) {
        // https://github.com/djungelorm/sphinx-tabs
        console.debug('Triggering Sphinx Tabs rendering');
        (function(d, script) {
            // HACK: please, improve this code to call the content of "tab.js" without creating a script element

            // Get the URL from the current generated page since it's not always the same
            var older_tabs_src = $('script[src$="sphinx_tabs/tabs.js"]');
            if (older_tabs_src.length != 0) {
                // sphinx-tabs < 2
                older_tabs_src = older_tabs_src[0].older_tabs_src
                script = d.createElement('script');
                script.type = 'text/javascript';
                script.onload = function(){
                    // remote script has loaded
                };
                script.older_tabs_src = older_tabs_src;
                d.getElementsByTagName('head')[0].appendChild(script);

                // Once the script has been executed, we remove it from the DOM
                script.parentNode.removeChild(script);
            }
            var newer_tabs_src = $('script[src$="_static/tabs.js"]');
            if (newer_tabs_src.length != 0) {
                // sphinx-tabs > 2
                // Borrowed from
                // https://github.com/executablebooks/sphinx-tabs/blob/0f3cbbe/sphinx_tabs/static/tabs.js#L8-L17
                var allTabs = document.querySelectorAll('.sphinx-tabs-tab');
                var tabLists = document.querySelectorAll('[role="tablist"]');
                allTabs.forEach(tab => {
                    tab.addEventListener("click", changeTabs);
                });

                tabLists.forEach(tabList => {
                    tabList.addEventListener("keydown", keyTabs);
                });
            }

        }(document));
    };
};

function getEmbedURL(url) {
    var params = {
        'doctool': 'sphinx',
        'doctoolversion': '8.1.3',
        'url': url,
    }
    console.debug('Data: ' + JSON.stringify(params));
    var url = '/_' + '/api/v3/embed/?' + $.param(params);
    console.debug('URL: ' + url);
    return url
}

function addTooltip(target) {
    return target.tooltipster({
        theme: ['tooltipster-shadow', 'tooltipster-shadow-custom'],
        interactive: true,
        maxWidth: 450,
        animation: 'fade',
        animationDuration: 0,
        side: 'right',
        content: 'Loading...',
        contentAsHTML: true,

        functionBefore: function(instance, helper) {
            var $origin = $(helper.origin);
            var href = $origin.prop('href');

            // we set a variable so the data is only loaded once via Ajax, not every time the tooltip opens
            if ($origin.data('loaded') !== true) {
                var url = getEmbedURL(href);
                $.ajax({
                    url: url,
                    headers: {'X-HoverXRef-Version': '1.4.2'},
                }).done(
                    function (data) {
                        // call the 'content' method to update the content of our tooltip with the returned data.
                        // note: this content update will trigger an update animation (see the updateAnimation option)
                        instance.content(data['content']);

                        // to remember that the data has been loaded
                        $origin.data('loaded', true);
                    }
                );
            }
        },

        functionReady: function(instance, helper) {
            // most of Read the Docs Sphinx theme bases its style on "rst-content".
            // We add that class to the tooltipser HTML tag here by default or a user-defined one.
            helper.tooltip.classList.add('rst-content');
            reLoadSphinxTabs();
            setTimeout(
                reRenderTooltip,
                50,
                instance,
                helper
            );
        }
    })
}


$(document).ready(function() {
    // Remove ``title=`` attribute for intersphinx nodes that have hoverxref enabled.
    // It doesn't make sense the browser shows the default tooltip (browser's built-in)
    // and immediately after that our tooltip was shown.

    // Support lazy-loading here by switching between on-page-load (calling .tooltipster directly)
    // or delaying it until after a mouseenter or click event.
    // On large pages (the use case for lazy-loaded tooltipster) this moves dom manipulation to
    // on-interaction, which is known to be less performant on small pages (as per tooltipster docs),
    // but on massive docs pages fixes an otherwise severe page load stall when tooltipster
    // manipulates the html for every single tooltip at once.
    
    $('.hxr-hoverxref.external').each(function () { $(this).removeAttr('title') });
    addTooltip(
        $('.hxr-hoverxref.hxr-tooltip')
    )
    


    var modalHtml = `
  <div class="modal micromodal-slide rst-content" id="micromodal" aria-hidden="true">
    <div class="modal__overlay" tabindex="-1" data-micromodal-close>
      <div class="modal__container" role="dialog" aria-modal="true" aria-labelledby="micromodal-title">
        <header class="modal__header">
          <h1 class="modal__title" id="micromodal-title"></h1>
          <button class="modal__close" aria-label="Close modal" data-micromodal-close></button>
        </header>
        <hr/>
        <main class="modal__content" id="micromodal-content"></main>
        <footer class="modal__footer">
          <button class="modal__btn" data-micromodal-close aria-label="Close this dialog window">Close</button>
        </footer>
      </div>
    </div>
  </div>
`
    $('body').append(modalHtml);

    
    function onShow(modal, element) {
        // This is a HACK to get some "smart" left position of the
        // modal depending its size.
        var container = $('#micromodal .modal__container')
        var maxWidth = $('.wy-nav-content').innerWidth() - 150;
        var contentLeft = $('.wy-nav-content').position().left;
        if (container.width() >= maxWidth) {
            var left = contentLeft - 150;
        }
        else {
            var left = contentLeft + 150;
        }
        console.debug('Container left position: ' + left);
        container.css('left', left);
    }
    

    function showModal(element) {
        var href = element.prop('href');
        var url = getEmbedURL(href);
        $.ajax({
            url: url,
            headers: {'X-HoverXRef-Version': '1.4.2'},
        }).done(
            function (data) {
                var content = $('<div></div>');
                content.html(data['content']);

                var h1 = $('h1:first', content);
                var title = h1.text()
                if (title) {
                    var link = $('a', h1).attr('href') || '#';

                    // Remove permalink icon from the title
                    var title = title.replace('¶', '').replace('', '');

                    var a = $('<a></a>').attr('href', link).text('📝 ' + title);
                }
                else {
                    var a = '📝 Note';
                }
                h1.replaceWith('');

                $('#micromodal-title').html(a);
                $('#micromodal-content').html(content);
                MicroModal.show('micromodal', {
                    
                    onShow: onShow,
                    
                    openClass: 'is-open',
                    disableScroll: false,
                    disableFocus: true,
                    awaitOpenAnimation: false,
                    awaitCloseAnimation: false,
                    debugMode: false
                });
                $('#micromodal .modal__container').scrollTop(0);
                reLoadSphinxTabs();
                if (mathjax) {
                    if (typeof MathJax !== 'undefined') {
                        reLoadMathJax('micromodal');
                    } else {
                        console.debug('Not triggering MathJax because it is not defined');
                    };
                };
            }
        );
    };

    var delay = 350, setTimeoutConst;
    $('.hxr-hoverxref.hxr-modal').hover(function(event) {
        var element = $(this);
        console.debug('Event: ' + event + ' Element: ' + element);
        event.preventDefault();

        setTimeoutConst = setTimeout(function(){
            showModal(element);
        }, delay);
    }, function(){
        clearTimeout(setTimeoutConst);
    });
});