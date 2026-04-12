/**
 * Держит splash-screen на EXTRA_MS дольше, чем задумано в Open WebUI.
 */
(function () {
  var EXTRA_MS = 3000;
  var origRemove = Element.prototype.remove;
  Element.prototype.remove = function () {
    if (this && this.id === "splash-screen") {
      var self = this;
      setTimeout(function () {
        origRemove.call(self);
      }, EXTRA_MS);
      return;
    }
    return origRemove.apply(this, arguments);
  };
  var origRemoveChild = Node.prototype.removeChild;
  Node.prototype.removeChild = function (child) {
    if (child && child.id === "splash-screen") {
      var self = this;
      setTimeout(function () {
        origRemoveChild.call(self, child);
      }, EXTRA_MS);
      return child;
    }
    return origRemoveChild.apply(this, arguments);
  };
})();
