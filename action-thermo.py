#!/usr/bin/env python3

from colors import css_colors
from snips_skill import *
import json, time


_, ngettext = get_translations( __file__)


class ThermoSkill( MultiRoomConfig, Skill):
    
    'Control thermometers and thermostats via MQTT'
    
    LOCATION_SLOT = 'room'
    
    ADJUSTMENTS = { # Synonyms for translation
        _('higher') : +1,
        _('warmer') : +1,
        _('cooler') : -1,
        _('lower')  : -1,
    }
    
    SETTINGS = {} # Stores device state, keyed by device name
    
    
    @staticmethod
    def status( self, userdata, msg):
        'Collect device status reports'
        self.log.debug( 'Received message: %s -> %s', msg.topic, msg.payload)
        value = None if msg.payload == b'off' else json.loads( msg.payload)
        self.SETTINGS[ msg.topic] = value


    def require_capability( self, msg, capability):
        'Check against the config that a given device can handle the requested action'
        caps = self.get_room_config( msg.payload).get( 'capabilities', '')
        if capability not in map( lambda s: s.strip(), caps.split( ',')):
            raise SnipsError( _("Sorry, that's impossible."))


    def get_topic( self, msg, key):
        conf = self.get_room_config( msg.payload)
        device = conf.get( 'device')
        topic = conf.get( key)
        if topic and device:
            return topic.format( device=device)


    def get_status( self, msg, key, error=_("Sorry, I don't know.")):
        topic = self.get_topic( msg, key)
        if topic and topic in self.SETTINGS:
            return self.SETTINGS[ topic]
        raise SnipsError( error)


    def get_statuses( self, key):
        for room, conf in self.configuration.items():
            device = conf.get( 'device')
            topic = conf.get( key)
            if topic and device:
                topic = topic.format( device=device)
                if topic in self.SETTINGS:
                    yield room, self.SETTINGS[ topic]


    @intent( 'dnknth:GetTargetTemperature')
    @min_confidence( 0.6)
    def get_target( self, userdata, msg):
        if self.all_rooms( msg.payload):
            readings = self.get_readings( 'get_target')
            initial, last = ', '.join( readings[:-1]), readings[-1]
            return ngettext(
                'The heating is set to {initial}{last}.',
                'The heating is set to {initial} and {last}.',
                len( readings)
            ).format( initial=initial, last=last)

        value = self.get_status( msg, 'get_target')
        return _('It is set to {degrees:n} degrees.').format(
            degrees=value)
    

    def get_readings( self, key):
        readings = [ _('{degrees:n} degrees {in_room}').format(
            degrees=degrees, in_room=room_with_preposition( room))
            for room, degrees in self.get_statuses( key) ]
        if not readings: raise SnipsError( _("Sorry, I don't know."))
        return readings
        

    @intent( 'dnknth:GetTemperature')
    @min_confidence( 0.6)
    def get_temperature( self, userdata, msg):
        if self.all_rooms( msg.payload):
            readings = self.get_readings( 'get_temp')
            initial, last = ', '.join( readings[:-1]), readings[-1]
            return ngettext(
                'It is {initial}{last}.',
                'It is {initial} and {last}.',
                len( readings)
            ).format( initial=initial, last=last)
                
        value = self.get_status( msg, 'get_temp')
        return _('It is {degrees:n} degrees.').format(
            degrees=value)


    def set_target(self, msg, value):
        set_topic = self.get_topic( msg, 'set_target')
        if not set_topic:
            raise SnipsError( "Sorry, I can't do that.")
        self.publish( set_topic, json.dumps( value))
        get_topic = self.get_topic( msg, 'get_target')
        self.SETTINGS[ get_topic] = value
        

    @intent( 'dnknth:SetTemperature')
    @min_confidence( 0.8)
    @require_slot( 'temperature', prompt=_('which temperature?'))
    def set_temperature( self, userdata, msg):
        self.require_capability( msg, 'set_target')
        value = msg.payload.slot_values[ 'temperature'].value
        self.set_target( msg, value)
        return _('It is set to {degrees:n} degrees.').format(
            degrees=value)


    @intent( 'dnknth:SetRelativeTemperature')
    @min_confidence( 0.7)
    @require_slot( 'adjustment', prompt=_('warmer or cooler?'))
    def adjust( self, userdata, msg):
        self.require_capability( msg, 'set_target')
        value = self.get_status( msg, 'get_target',
            _("Sorry, I con't do this right now."))
            
        adjustment = msg.payload.slot_values[ 'adjustment'].value
        value += self.ADJUSTMENTS.get( adjustment, 0)
        self.set_target( msg, value)
        return _('It is set to {degrees:n} degrees.').format(
            degrees=value)

            
    def run( self):
        with self.connect():
            conf = self.configuration['DEFAULT']
            probes = conf.get( 'probes', '').split( ',')
            for topic in probes:
                topic = conf[ topic.strip()].format( device='+')
                self.subscribe( topic, qos=1)
                self.message_callback_add( topic, self.status)
                self.log.debug( "Subscribed to MQTT topic: %s", topic)
                
            self.loop_forever()


if __name__ == '__main__':
    
    ThermoSkill().run()
