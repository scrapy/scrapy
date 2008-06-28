
(function($){
  
  
  /*
   Text field auto-completion plugin for jQuery.
   Based on http://www.dyve.net/jquery/?autocomplete by Dylan Verheul.
  */
  $.suggest = function(input, url, paramName, minChars, delay) {
    var input = $(input).addClass("suggest").attr("autocomplete", "off");
    var timeout = null;
    var prev = "";
    var selectedIndex = -1;
    var results = null;
  
    input.keydown(function(e) {
      switch(e.keyCode) {
        case 27: // escape
          hide();
          break;
        case 38: // up
        case 40: // down
          e.preventDefault();
          if (results) {
            var items = $("li", results);
            if (!items) return;
            var index = selectedIndex + (e.keyCode == 38 ? -1 : 1);
            if (index >= 0 && index < items.length) {
              move(index);
            }
          } else {
            show();
          }
          break;
        case 9:  // tab
        case 13: // return
        case 39: // right
          if (results) {
            var li = $("li.selected", results);
            if (li.length) {
              select(li);
              e.preventDefault();
            }
          }
          break;
        default:
          if (timeout) clearTimeout(timeout);
          timeout = setTimeout(show, delay);
          break;
      }
    });
    input.blur(function() {
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(hide, 200);
    });
  
    function hide() {
      if (timeout) clearTimeout(timeout);
      input.removeClass("loading");
      if (results) {
        results.fadeOut("fast").remove();
        results = null;
      }
      $("iframe.iefix").remove();
      selectedIndex = -1;
    }
  
    function move(index) {
      if (!results) return;
      items = $("li", results);
      items.removeClass("selected");
      $(items[index]).addClass("selected");
      selectedIndex = index;
    }
  
    function select(li) {
      if (!li) li = $("<li>");
      else li = $(li);
      var val = $.trim(li.text());
      prev = val;
      input.val(val);
      hide();
      selectedIndex = -1;
    }
  
    function show() {
      var val = input.val();
      if (val == prev) return;
      prev = val;
      if (val.length < minChars) { hide(); return; }
      input.addClass("loading");
      var params = {};
      params[paramName] = val;
      $.get(url, params, function(data) {
        if (!data) { hide(); return; }
        if (!results) {
          var offset = input.offset();
          results = $("<div>").addClass("suggestions").css({
            position: "absolute",
            minWidth: input.get(0).offsetWidth + "px",
            top:  (offset.top + input.get(0).offsetHeight) + "px",
            left: offset.left + "px",
            zIndex: 2
          }).appendTo("body");
          if ($.browser.msie) {
            var iframe = $("<iframe style='display:none;position:absolute;" +
              "filter:progid:DXImageTransform.Microsoft.Alpha(opacity=0);'" +
              " class='iefix' src='javascript:false;' frameborder='0'" +
              " scrolling='no'></iframe>").insertAfter(results);
            setTimeout(function() {
              var offset = getOffset(results);
              iframe.css({
                top: offset.top + "px",
                right: (offset.left + results.get(0).offsetWidth) + "px",
                bottom: (offset.top + results.get(0).offsetHeight) + "px",
                left: offset.left + "px",
                zIndex: 1
              });
              iframe.show();
            }, 10);
          }
        }
        results.html(data).fadeTo("fast", 0.92);
        items = $("li", results);
        items
          .hover(function() { move(items.index(this)) },
                 function() { $(this).removeClass("selected") })
          .click(function() { select(this); input.get(0).focus() });
        move(0);
      });
    }
  }
  
  $.fn.suggest = function(url, paramName, minChars, delay) {
    url = url || window.location.pathname;
    paramName = paramName || 'q';
    minChars = minChars || 1;
    delay = delay || 400;
    return this.each(function() {
      new $.suggest(this, url, paramName, minChars, delay);
    });
  }

})(jQuery);
