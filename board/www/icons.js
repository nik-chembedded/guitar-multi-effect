/* Line icons of the effects (24 x 24, drawn in the current text colour).  params.json names the icon
   of each effect ("icon"); an unknown name gets the generic one. */
"use strict";
(function () {
  var P = {
    /* gain-reduction needle */
    compressor: '<path d="M3.5 17.5a8.5 8.5 0 0 1 17 0"/><path d="M12 17.5l4.2-5.2"/>' +
                '<circle cx="12" cy="17.5" r="1.3" fill="currentColor"/><path d="M6 11.5l1.1 1.1M12 9v1.6M18 11.5l-1.1 1.1"/>',
    /* soft-clipped wave */
    overdrive: '<path d="M2 12C3.5 7.5 5 6 7.5 6H9c2 0 2.5 3 3 6s1 6 3 6h1.5c2.5 0 4-1.5 5.5-6"/>',
    /* hard-clipped wave with fuzz on the flats */
    distortion: '<path d="M2 12l1.8-6l1.35 1.2 1.35-1.2 1.35 1.2 1.35-1.2L12 12l2.8 6l1.35-1.2 1.35 1.2 1.35-1.2 1.35 1.2L22 12"/>',
    /* speaker cabinet */
    cabinet: '<rect x="4" y="2.5" width="16" height="19" rx="2"/><circle cx="12" cy="14.5" r="4.5"/>' +
             '<circle cx="12" cy="14.5" r="1.3"/><circle cx="12" cy="6.5" r="1.3"/>',
    /* three faders */
    eq: '<path d="M6 3.5v17M12 3.5v17M18 3.5v17"/><rect x="3.8" y="13" width="4.4" height="3" rx="1" fill="currentColor"/>' +
        '<rect x="9.8" y="6.5" width="4.4" height="3" rx="1" fill="currentColor"/><rect x="15.8" y="10.5" width="4.4" height="3" rx="1" fill="currentColor"/>',
    /* two voices out of phase */
    chorus: '<path d="M2 9.5c2-4 4-4 5 0s3 4 5 0 3-4 5 0 3 4 5 0"/>' +
            '<path d="M2 14.5c2 4 4 4 5 0s3-4 5 0 3 4 5 0 3-4 5 0" opacity=".55"/>',
    /* amplitude rising and falling */
    tremolo: '<path d="M3 11v2M5.25 9v6M7.5 7v10M9.75 9v6M12 11v2M14.25 9v6M16.5 7v10M18.75 9v6M21 11v2"/>',
    /* one note and its fading repeats */
    echo: '<path d="M2 12c1-6 2.5-6 3 0s2 6 3 0"/><path d="M9.5 12c.8-4 2-4 2.5 0s1.7 4 2.5 0" opacity=".65"/>' +
          '<path d="M16 12c.6-2.2 1.4-2.2 1.8 0s1.2 2.2 1.8 0" opacity=".4"/>',
    /* a hall */
    reverb: '<path d="M3 20.5V9.5l9-6 9 6v11"/><path d="M3 20.5h18"/><path d="M7.5 17a4.5 4.5 0 0 1 9 0"/><path d="M10 17a2 2 0 0 1 4 0"/>',
    generic: '<circle cx="12" cy="12" r="8"/><path d="M8 12h8"/>'
  };
  GME.iconNames = Object.keys(P);
  GME.icon = function (name) {
    var s = document.createElement("span");
    s.className = "ico";
    s.setAttribute("aria-hidden", "true");
    s.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" ' +
                  'stroke-linejoin="round">' + (P[name] || P.generic) + '</svg>';
    return s;
  };
})();
