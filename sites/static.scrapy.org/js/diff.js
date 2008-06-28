(function($){
  
  function convertDiff(name, table) {
    var inline = table.className == 'inline';
    var ths = table.tHead.rows[0].cells;
    var afile, bfile;
    if ( inline ) {
        afile = ths[0].title;
        bfile = ths[1].title;
    } else {
        afile = $(ths[0]).find('a').text();
        bfile = $(ths[1]).find('a').text();
    }
    if ( afile.match(/^Revision /) ) {
        afile = 'a/' + name;
        bfile = 'b/' + name;
    }
    var lines = [
      "Index: " + name,
      "===================================================================",
      "--- " + afile.replace(/File /, ''),
      "+++ " + bfile.replace(/File /, ''),
    ];
    var sepIndex = 0;
    var oldOffset = 0, oldLength = 0, newOffset = 0, newLength = 0;
  
    for (var i = 0; i < table.tBodies.length; i++) {
      var tBody = table.tBodies[i];
      if (i == 0 || tBody.className == "skipped") {
        if (i > 0) {
          if (!oldOffset && oldLength) oldOffset = 1
          if (!newOffset && newLength) newOffset = 1
          lines[sepIndex] = lines[sepIndex]
            .replace("{1}", oldOffset).replace("{2}", oldLength)
            .replace("{3}", newOffset).replace("{4}", newLength);
        }
        sepIndex = lines.length;
        lines.push("@@ -{1},{2} +{3},{4} @@");
        oldOffset = 0, oldLength = 0, newOffset = 0, newLength = 0;
        if (tBody.className == "skipped") continue;
      }
      var tmpLines = [];
      for (var j = 0; j < tBody.rows.length; j++) {
        var cells = tBody.rows[j].cells;
        var oldLineNo = parseInt($(cells[0]).text());
        var newLineNo = parseInt($(cells[inline ? 1 : 2]).text());
        if (tBody.className == 'unmod') {
          lines.push(" " + $(cells[inline ? 2 : 1]).text());
          oldLength += 1;
          newLength += 1;
          if (!oldOffset) oldOffset = oldLineNo;
          if (!newOffset) newOffset = newLineNo;
        } else {
          var oldLine;
          var newLine;
          if (inline) {
            oldLine = newLine = $(cells[2]).text();
          } else {
            oldLine = $(cells[1]).text();
            newLine = $(cells[3]).text();
          }
          if (!isNaN(oldLineNo)) {
            lines.push("-" + oldLine);
            oldLength += 1;
          }
          if (!isNaN(newLineNo)) {
            tmpLines.push("+" + newLine);
            newLength += 1;
          }
        }
      }
      if (tmpLines.length > 0) {
        lines = lines.concat(tmpLines);
      }
    }
  
    if (!oldOffset && oldLength) oldOffset = 1;
    if (!newOffset && newLength) newOffset = 1;
    lines[sepIndex] = lines[sepIndex]
      .replace("{1}", oldOffset).replace("{2}", oldLength)
      .replace("{3}", newOffset).replace("{4}", newLength);
  
    /* remove trailing &nbsp; and join lines (with CR for IExplorer) */
    for ( var i = 0; i < lines.length; i++ )
        if ( lines[i] )
            lines[i] = lines[i].replace(/\xa0$/, '');
    return lines.join($.browser.msie ? "\r" : "\n");
  }
  
  $(document).ready(function($) {
    $("div.diff h2").each(function() {
      var switcher = $("<span class='switch'></span>").prependTo(this);
      var name = $.trim($(this).text());
      var table = $(this).siblings("table").get(0);
      if (! table) return;
      var pre = $("<pre></pre>").hide().insertAfter(table);
      $("<span>Tabular</span>").click(function() {
        $(pre).hide();
        $(table).show();
        $(this).addClass("active").siblings("span").removeClass("active");
        return false;
      }).addClass("active").appendTo(switcher);
      $("<span>Unified</span>").click(function() {
        $(table).hide();
        if (!pre.get(0).firstChild) pre.text(convertDiff(name, table));
        $(pre).fadeIn("fast")
        $(this).addClass("active").siblings("span").removeClass("active");
        return false;
      }).appendTo(switcher);
    });
  });

})(jQuery);
