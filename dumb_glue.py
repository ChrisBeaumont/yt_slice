from yt_slice import YtSlice

from glue.core import Component


class YtComponent(Component):

    def __init__(self, data, pf, field):
        super(YtComponent, self).__init__(data)
        self._y = YtSlice(pf, field)
        self._last = None

    def __getitem__(self, view):
        if len([v for v in view if isinstance(v, int)]) != 1:
            print "-3D"
            return super(YtComponent, self).__getitem__(view)

        for v in view:
            if not isinstance(v, (slice, int)):
                print "fancy"
                return super(YtComponent, self).__getitem__(view)

        if self._last == view:
            print "cache"
            return self._last_result

        print 'YT, BITCHES!!!!'
        result = self._y[view]
        self._last = view
        self._last_result = result
        return result


if __name__ == "__main__":

    from glue.core import Data, DataCollection
    from glue.qt import GlueApplication
    from yt.frontends.stream.api import load_uniform_grid
    import numpy as np

    from astropy.io import fits

    data = fits.open('../paws_correct.fits', memmap=False)[0].data
    data = np.squeeze(data)
    x = data
    shp = data.shape

    pf = load_uniform_grid(dict(data=data), shp, 1)
    d = Data(label='data')
    d.add_component(YtComponent(x, pf, 'data'), label='x')

    dc = DataCollection(d)

    ga = GlueApplication(dc)
    ga.start()
