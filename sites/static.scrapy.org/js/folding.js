(function($){

  $.fn.enableFolding = function(autofold) {
    var fragId = document.location.hash;
    if (fragId && /^#no\d+$/.test(fragId)) {
      fragId = parseInt(fragId.substr(3));
    }
  
    var count = 1;
    return this.each(function() {
      var t = $(this).text();
      $(this).text("");
      var trigger = $(this).append("<a href='#no" + count + "'></a>").children();
      trigger.text(t);
  
       trigger.click(function() {
         if (fragId == count) { fragId = 0; return; }
         $(this.parentNode.parentNode).toggleClass("collapsed");
       });
       if ( autofold )
         trigger.click();
      count++;
    }).css("cursor", "pointer");
  }

})(jQuery);