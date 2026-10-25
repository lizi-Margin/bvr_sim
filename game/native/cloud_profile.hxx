#pragma once
#include "WickedEngine.h"
#include "json.hpp"
#include <cmath>
#include <stdexcept>

// Presentation-only weather configuration. Missing cloud_layer preserves the
// pinned engine defaults. Validate a copy before changing live weather.
inline void apply_cloud_profile(wi::scene::WeatherComponent& weather, const nlohmann::json& profile) {
    if (!profile.is_object()) return;
    const auto haze=profile.value("horizon_height_fog",nlohmann::json::object());
    weather.SetOverrideFogColor(haze.contains("color_linear"));
    if(haze.contains("color_linear")){
        const auto color=haze.at("color_linear").get<std::array<float,3>>();
        for(float value:color)if(!std::isfinite(value)||value<0||value>4)throw std::invalid_argument("Invalid height-fog color");
        weather.horizon={color[0],color[1],color[2]};
    }
    // A baked data texture supplies coverage/type/rain in linear RGB. Retain
    // the existing volumetric ray marcher; this is not a sky photograph.
    if(profile.contains("cloud_weather_map")){
        const auto& source=profile.at("cloud_weather_map");
        if(!source.is_object()||!source.contains("file"))throw std::invalid_argument("cloud_weather_map requires a file");
        const auto file=source.at("file").get<std::string>();
        auto resource=wi::resourcemanager::Load(file,wi::resourcemanager::Flags::IMPORT_RETAIN_FILEDATA);
        if(!resource.IsValid())throw std::invalid_argument("Cannot load cloud weather map: "+file);
        const auto& desc=resource.GetTexture().GetDesc();
        if(desc.format!=wi::graphics::Format::R8G8B8A8_UNORM||desc.width<128||desc.height<128||desc.width>4096||desc.height>4096)
            throw std::invalid_argument("Cloud weather map requires linear RGBA8,128..4096 pixels");
        weather.volumetricCloudsWeatherMapFirst=std::move(resource);
        weather.volumetricCloudsWeatherMapFirstName=file;
    }else{
        weather.volumetricCloudsWeatherMapFirst=wi::Resource();
        weather.volumetricCloudsWeatherMapFirstName.clear();
    }
    if(!profile.contains("cloud_layer"))return;
    const auto& layer = profile.at("cloud_layer");
    if (!layer.is_object()) throw std::invalid_argument("cloud_layer must be an object");
    auto candidate = weather.volumetricCloudParameters;
    auto set = [&](const char* name, float& value, float minimum, float maximum) {
        if (!layer.contains(name)) return;
        const float requested = layer.at(name).get<float>();
        if (!std::isfinite(requested) || requested < minimum || requested > maximum)
            throw std::invalid_argument(std::string("Invalid cloud_layer parameter: ") + name);
        value = requested;
    };
    set("base_height_m", candidate.cloudStartHeight, 0.f, 25000.f);
    set("thickness_m", candidate.cloudThickness, 100.f, 20000.f);
    set("coverage", candidate.layerFirst.coverageAmount, 0.f, 2.f);
    set("type", candidate.layerFirst.typeAmount, 0.f, 1.f);
    set("noise_scale_per_m", candidate.layerFirst.totalNoiseScale, .00001f, .01f);
    set("weather_scale_per_m", candidate.layerFirst.weatherScale, .000001f, .01f);
    set("second_layer_coverage", candidate.layerSecond.coverageAmount, 0.f, 2.f);
    if (layer.contains("ray_steps")) {
        const int steps=layer.at("ray_steps").get<int>();
        if(steps<16||steps>2048)throw std::invalid_argument("cloud_layer ray_steps must be16..2048");
        candidate.maxStepCount=steps;
    }
    set("step_distribution_m", candidate.inverseDistanceStepCount, 100.f, 100000.f);
    set("initial_step_scale", candidate.bigStepMarch, 1.f, 8.f);
    set("shadow_samples", candidate.shadowSampleCount, 1.f, 64.f);
    set("ground_samples", candidate.groundContributionSampleCount, 1.f, 64.f);
    weather.volumetricCloudParameters = candidate;
}
