import sys
import argparse

try:
    import requests
    import simplekml
    import polyline
except ModuleNotFoundError:
    yn = input('It looks like you are missing the required libraries. Would you like to install them now? [Y|n] ')
    if yn.lower().startswith('y') or len(yn) == 0:
        import pip
        print('Installing required libraries...')
        pip.main(['install', '-r', 'requirements.txt'])
        print('Libraries installed.\n\n')
    else:
        sys.exit(0)

URL = 'https://maps.roadtrippers.com/api/v2/trips/%s'

def MakeWaypointKMLEntry(kml, waypoint):
    kml.newpoint(name=waypoint['name'], coords=[(waypoint['start_location'][0], waypoint['start_location'][1])])
    if waypoint['start_location'][0] != waypoint['end_location'][0] or waypoint['start_location'][1] != waypoint['end_location'][1]:
        kml.newpoint(name=waypoint['name'], coords=[(waypoint['end_location'][0], waypoint['end_location'][1])])

def MakeTrack(kml, day, coords, distance):
    import simplekml
    ls = kml.newlinestring(name="Day %02d"%(day+1))
    ls.coords = coords
    ls.extrude = 1
    ls.altitudemode = simplekml.AltitudeMode.clamptoground
    ls.style.linestyle.width = 5
    ls.style.linestyle.color = simplekml.Color.cornflowerblue
    ls.description = "Distance: %d" % distance
    return ls

def export(trip_ids, kmlname='', no_waypoints=False, no_paths=False, no_group_days=False, split_wpt_days=False, debug=False):
    import requests
    import simplekml
    import polyline
    kml = simplekml.Kml()
    for id in trip_ids:
        try:
            fullURL = URL % id
            print("Getting trip details from '%s'" % fullURL)
            resp = requests.get(fullURL)
            if resp.status_code == 404:
                print('Error 404\nCould not find trip %s' % id)
                continue
            if resp.status_code != 200:
                print('Error %s trying to find trip %s' % (resp.status_code, id))
                continue
            if debug:
                fn = 'response_%s.json' % id
                print("  Saving JSON response to '%s'" % fn)
                with open(fn, 'wb') as f:
                    f.write(resp.content)
            data = resp.json()
            trip = data['trip']
            waypoints = trip['waypoints']
            legs = trip['legs']
            waypoint_start_date = {}
            waypoint_name = {}

            # Do waypoints first so we can build the list of waypoint IDs that indicate the end of a day's travelling
            day = 0
            if not no_waypoints:
                print("  Generating waypoints...")
                # Check every waypoint has a date. Those without a date will have the date from the next following dated entry applied.
                if split_wpt_days:
                    last_waypoint = waypoints[-1]
                    last_date = last_waypoint['start_date']
                    if not last_date:
                        print("  ERROR: When splitting days of trip, last waypoint must have an associated date")
                        quit()
                    for waypoint in reversed(waypoints):
                        if not waypoint['start_date']:
                            waypoint['start_date'] = last_date
                        else:
                            last_date = waypoint['start_date']

                first_waypoint = waypoints[0]
                last_date = first_waypoint['start_date']

                for i in range(len(waypoints)):
                    waypoint = waypoints[i]

                    # See if the waypoint has a date, if so save it with the ID. The last waypoint with a given date will be
                    # the one stored in the dict, which allows us to later determine which leg represnts the last leg of a given day.
                    start_date = waypoint['start_date']
                    id = waypoint['id']
                    if start_date:
                        waypoint_start_date[start_date] = id
                    waypoint_name[id] = waypoint['name']

                    if split_wpt_days and (start_date != last_date):
                        last_date = start_date

                        # Write out KML for the day
                        day = day + 1
                        fn = kmlname + '-'.join(trip_ids) + '-Day%02d' % (day) + '.kml'
                        kml.document.name = "Day%02d" % day
                        kml.save(fn)
                        print('      KML file saved to %s' % fn)

                        # Start a new KML with the previous waypoint
                        kml = simplekml.Kml()
                        MakeWaypointKMLEntry(kml, waypoints[i-1])
                        print("    Start of day Waypoint: %s (%s)" % (waypoints[i-1]['name'], waypoints[i-1]['start_date']))

                    print("      Waypoint: %s (%s)" % (waypoint['name'], waypoint['start_date']))
                    MakeWaypointKMLEntry(kml, waypoint)

                if split_wpt_days:
                    # Write out KML for the day
                    day = day + 1
                    fn = kmlname + '-'.join(trip_ids) + '-Day%02d' % (day) + '.kml'
                    kml.document.name = "Day%02d" % day
                    kml.save(fn)
                    print('      KML file saved to %s' % fn)

                    # Start a new KML with the previous waypoint
                    kml = simplekml.Kml()

            # Do paths (in KML-speak, or "track" in GPX-speak or "leg" in RT-speak)
            if not no_paths:
                print("  Generating tracks...")
                coords = []
                day = 0
                distance = 0
                waypoint_index = 0
                commit = False
                for leg in legs:
                    end_waypoint_id = leg['end_waypoint_id']
                    distance = distance + leg['distance'] / 1.609   # Add leg distance (kilometers) to overall day distance (miles)
                    coords.extend([(c[1], c[0], 0.0) for c in polyline.decode(leg['encoded_polyline'])])
                    waypoint_index = waypoint_index + 1
              
                    if no_group_days:
                        commit = True
                    elif end_waypoint_id in waypoint_start_date.values():
                        name = waypoint_name[end_waypoint_id] if end_waypoint_id in waypoint_name else ''
                        print("    Found end of day %2d in leg %2d  (%d miles to %s)" % (day+1, waypoint_index, distance, name))
                        commit = True
                    else:
                        commit = False
              
                    if (commit):
                        MakeTrack(kml, day, coords, distance)
                        coords = []
                        distance = 0
                        day = day + 1

                # Don't forget the last segment commit in case the last waypoint has no date
                if (not commit):
                    if not no_group_days:
                        name = waypoint_name[end_waypoint_id] if end_waypoint_id in waypoint_name else ''
                        print("    Found end of day %2d in leg %2d  (%d miles to %s)" % (day+1, waypoint_index, distance, name))
                    MakeTrack(kml, day, coords, distance)

        except:
            e = sys.exc_info()[0]
            print('Error parsing trip %s : %s' % (id, sys.exc_info()))

    fn = kmlname + '-'.join(trip_ids) + '.kml'
    kml.save(fn)
    print('KML file saved to %s' % fn)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('trip_id', nargs='+', help='The ID(s) of the trip(s) you want to export.')
    parser.add_argument('--no-waypoints', action='store_true', help='Omit waypoints from the KML.')
    parser.add_argument('--no-paths', action='store_true', help='Omit paths from the KML.')
    parser.add_argument('--no-group-days', action='store_true', help='Do not group individual tracks into days based on dates.')
    parser.add_argument('--split-wpt-days', action='store_true', help='Split waypoints for each day''s travel into separate KML files.')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debugging, save JSON response to file.')
    parser.add_argument('-n', '--name', action='store', help='Set output KML filename prefix', default='')
    args = parser.parse_args()
    export(args.trip_id, args.name, args.no_waypoints, args.no_paths, args.no_group_days, args.split_wpt_days, args.debug)
