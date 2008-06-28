// Enable expanding/folding folders in TracBrowser

(function($){
  var FOLDERID_COUNTER = 0;
  var SUBFOLDER_INDENT = 20;
  
  // enableExpandDir adds the capability to folder rows to be expanded and folded
  // It also teach the rows about their ancestors. It expects:
  //  - `parent_tr`, the logical parent row (`null` if there's no ancestor)
  //  - a `rows` jQuery object matching the newly created entry rows
  //  - `qargs`, additional parameters to send to the server when expanding
  
  window.enableExpandDir = function(parent_tr, rows, qargs) {
    // the ancestors folder ids are present in the parent_tr class attribute
    var ancestor_folderids = [];
    if (parent_tr)
      ancestor_folderids = $.grep(parent_tr.attr("class").split(" "), 
                                  function(c) { return c.match(/^f\d+$/)});
    rows.each(function () {
      var a = $(this).find("a.dir");
  
      if (a.length) { // then the entry is a folder
        // create new folder id
        var folderid = "f" + FOLDERID_COUNTER++;
        this.id = folderid;
        $(this).addClass(folderid);
  
        // add the expander icon
        a.wrap('<div></div>');
        var expander = a.before('<span class="expander">&nbsp;</span>').prev();
        expander.attr("title", "Expand sub-directory in place")
          .click(function() { toggleDir($(this), qargs); });
      }
  
      // tie that row to ancestor folders
      if (parent_tr)
        $(this).addClass(ancestor_folderids.join(" "));
    });
  }
  
  // handler for click event on the expander icons
  window.toggleDir = function(expander, qargs) {
    var tr = expander.parents("tr");
    var folderid = tr.get(0).id;
  
    if ( tr.filter(".expanded").length ) { // then *fold*
      tr.removeClass("expanded").addClass("collapsed");
      tr.siblings("tr."+folderid).hide();
      expander.attr("title", "Re-expand directory");
      return;
    }
  
    if ( tr.filter(".collapsed").length ) { // then *expand*
      tr.removeClass("collapsed").addClass("expanded");
      tr.siblings("tr."+folderid).show();
      // Note that the above will show all the already fetched subtree,
      // so we have to fold again the folders which were already collapsed.
      tr.siblings("tr.collapsed").each(function() {
        tr.siblings("tr."+this.id).not(this).hide();
      });
    } else {                                // then *fetch*
      var td = expander.parents("td");
      var td_class = td.attr("class");
      var a = expander.next("a");
      var depth = 
        parseFloat(td.css("padding-left").replace(/^(\d*\.\d*).*$/, "$1")) + 
        SUBFOLDER_INDENT;
  
      tr.addClass("expanded");
      // insert "Loading ..." row
      tr.after('<tr><td><span class="loading"></span></td></tr>');
      var loading_row = tr.next();
      loading_row.children("td").addClass(td_class)
        .attr("colspan", tr.children("td").length)
        .css("padding-left", depth);
      loading_row.find("span.loading").text("Loading " + a.text() + "...");
  
      // XHR for getting the rows corresponding to the folder entries
      $.ajax({
        type: "GET",
        url: a.attr("href"),
        data: qargs,
        dataType: "html",
        success: function(data) {
          // Safari 3.1.1 has some trouble reconstructing HTML snippets
          // bigger than 50k - splitting in rows before building DOM nodes
          var rows = data.replace(/^<!DOCTYPE[^>]+>/, "").split("</tr>");
          if (rows.length) {
            // insert entry rows 
            $(rows).each(function() {
              row = $(this+"</tr>");
              row.children("td."+td_class).css("padding-left", depth);
              // make all entry rows collapsible but only subdir rows expandable
              enableExpandDir(tr, row, qargs); 
              loading_row.before(row);
            });
            // remove "Loading ..." row
            loading_row.remove();
          } else {
            loading_row.find("span.loading").text("").append("<i>(empty)</i>")
              .removeClass("loading");
            // make the (empty) row collapsible
            enableExpandDir(tr, loading_row, qargs); 
          }
        },
        error: function(req, err, exc) {
          loading_row.find("span.loading").text("").append("<i>(error)</i>")
            .removeClass("loading");
          enableExpandDir(tr, loading_row, qargs);
        }
      });
    }
    expander.attr("title", "Fold directory");
  }

})(jQuery);
