
(function($){
  
  /* Adapted from http://www.kryogenix.org/code/browser/searchhi/ */
  $.fn.highlightText = function(text, className) {
    function highlight(node) {
      if (node.nodeType == 3) { // Node.TEXT_NODE
        var val = node.nodeValue;
        var pos = val.toLowerCase().indexOf(text);
        if (pos >= 0 && !$.className.has(node.parentNode, className)) {
          var span = document.createElement("span");
          span.className = className;
          span.appendChild(document.createTextNode(val.substr(pos, text.length)));
          node.parentNode.insertBefore(span, node.parentNode.insertBefore(
            document.createTextNode(val.substr(pos + text.length)),
              node.nextSibling));
          node.nodeValue = val.substr(0, pos);
        }
      } else if (!$(node).is("button, select, textarea")) {
        $.each(node.childNodes, function() { highlight(this) });
      }
    }
    return this.each(function() { highlight(this) });
  }
  
  $(document).ready(function() {
    var elems = $(".searchable");
    if (!elems.length) return;
  
    function getSearchTerms(url) {
      if (url.indexOf("?") == -1) return [];
      var params = url.substr(url.indexOf("?") + 1).split("&");
      for (var p in params) {
        var param = params[p].split("=");
        if (param.length < 2) continue;
        if (param[0] == "q" || param[0] == "p") { // q= for Google, p= for Yahoo
          var query = decodeURIComponent(param[1].replace(/\+/g, " "));
          if (query[0] == "!") query = query.slice(1);
          var terms = [];
          $.each(query.split(/(".*?")|('.*?')|(\s+)/), function() {
            term = this.replace(/^\s+$/, "");
            if (term.length) {
              terms.push(term.replace(/^['"]/, "").replace(/['"]$/, ""));
            }
          });
          return terms;
        }
      }
      return [];
    }
  
    var terms = getSearchTerms(document.URL);
    if (!terms.length) terms = getSearchTerms(document.referrer);
    $.each(terms, function(idx) {
      elems.highlightText(this.toLowerCase(), "searchword" + (idx % 5));
    });
  });

})(jQuery);