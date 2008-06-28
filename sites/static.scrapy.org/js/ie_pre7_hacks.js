jQuery(function($) {  // onload
    $('select').bind('focusin', function() {
        this.tmpIndex = this.selectedIndex;
    }).bind('focus', function() {
        this.selectedIndex = this.tmpIndex;
    });
});
